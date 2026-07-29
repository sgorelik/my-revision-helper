"""
Tests for model selection and the call wrapper.

The two generations of model take different parameters, and a model being
listed by the API is not the same as the account being allowed to call it.
Both caught us out, so both are pinned down here.
"""

import pytest
from unittest.mock import MagicMock

import my_revision_helper.llm as llm
from my_revision_helper.llm import (
    EVERYDAY_MODELS,
    REASONING_MODELS,
    chat_completion,
    get_openai_model,
    get_reasoning_model,
)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Nothing learned in one test should leak into the next."""
    llm._legacy_params.clear()
    llm._unavailable.clear()
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_PARSING_MODEL", raising=False)
    yield
    llm._legacy_params.clear()
    llm._unavailable.clear()


def _client(*outcomes):
    """A client whose calls return, or raise, the given outcomes in order."""
    client = MagicMock()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1] if len(calls) <= len(outcomes) else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client.chat.completions.create.side_effect = create
    return client, calls


class TestParameterDialects:
    def test_older_models_get_max_tokens_and_the_chosen_temperature(self):
        client, calls = _client()

        chat_completion(client, model="gpt-4o", messages=[], temperature=0, max_tokens=500)

        assert calls[0]["max_tokens"] == 500
        assert calls[0]["temperature"] == 0
        assert "max_completion_tokens" not in calls[0]

    def test_newer_models_get_max_completion_tokens_and_no_temperature(self):
        client, calls = _client()

        chat_completion(client, model="gpt-5.6-sol", messages=[], temperature=0, max_tokens=500)

        # Temperature is rejected outright by these models, so it must not be sent.
        assert "temperature" not in calls[0]
        assert "max_tokens" not in calls[0]
        assert calls[0]["max_completion_tokens"] > 500

    def test_newer_models_get_room_to_think_before_answering(self):
        """Reasoning counts against the ceiling, so a 4o-sized budget truncates."""
        client, calls = _client()

        chat_completion(client, model="gpt-5.5", messages=[], max_tokens=2000)

        assert calls[0]["max_completion_tokens"] >= 4000

    def test_a_model_that_wants_the_other_dialect_is_retried(self):
        refusal = Exception(
            "Error code: 400 - Unsupported parameter: 'max_tokens' is not supported "
            "with this model. Use 'max_completion_tokens' instead."
        )
        client, calls = _client(refusal)

        # Named like an old model, but behaves like a new one.
        chat_completion(client, model="gpt-4o-experimental", messages=[], max_tokens=100)

        assert len(calls) == 2
        assert "max_tokens" in calls[0]
        assert "max_completion_tokens" in calls[1]

    def test_the_dialect_is_remembered_so_it_is_only_learned_once(self):
        refusal = Exception("Unsupported parameter: 'max_tokens' is not supported")
        client, calls = _client(refusal)

        chat_completion(client, model="gpt-4o-experimental", messages=[], max_tokens=100)
        chat_completion(client, model="gpt-4o-experimental", messages=[], max_tokens=100)

        assert len(calls) == 3  # two on the first call, one on the second
        assert "max_completion_tokens" in calls[2]

    def test_an_unrelated_error_is_not_retried(self):
        client, calls = _client(Exception("Error code: 500 - server had a problem"))

        with pytest.raises(Exception, match="server had a problem"):
            chat_completion(client, model="gpt-4o", messages=[], max_tokens=100)

        assert len(calls) == 1


class TestFallingBackWhenAModelIsOutOfReach:
    def test_a_tier_the_plan_does_not_cover_drops_to_the_next_model(self):
        """A model can be listed by /models and still refuse every call."""
        no_quota = Exception(
            "Error code: 429 - You exceeded your current quota, please check your "
            "plan and billing details. insufficient_quota"
        )
        client, calls = _client(no_quota)

        chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)

        assert [c["model"] for c in calls] == REASONING_MODELS[:2]

    def test_a_dead_model_is_not_asked_for_again(self):
        no_quota = Exception("insufficient_quota")
        client, calls = _client(no_quota)

        chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)
        chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)

        assert [c["model"] for c in calls] == [
            REASONING_MODELS[0],
            REASONING_MODELS[1],
            REASONING_MODELS[1],
        ]
        assert get_reasoning_model() == REASONING_MODELS[1]

    def test_an_ordinary_rate_limit_does_not_downgrade_anything(self):
        """Being briefly too busy is not a reason to mark a model dead."""
        client, calls = _client(Exception("Error code: 429 - Rate limit reached, try again in 2s"))

        with pytest.raises(Exception, match="Rate limit"):
            chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)

        assert len(calls) == 1
        assert get_reasoning_model() == REASONING_MODELS[0]

    def test_a_model_that_is_not_a_chat_model_is_skipped(self):
        """The -pro variants answer /models but reject chat completions."""
        client, calls = _client(
            Exception("Error code: 404 - This is not a chat model and thus not supported")
        )

        chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)

        assert len(calls) == 2

    def test_the_error_surfaces_when_nothing_in_the_ladder_answers(self):
        client, _ = _client(*[Exception("insufficient_quota")] * (len(REASONING_MODELS) + 2))

        with pytest.raises(Exception, match="insufficient_quota"):
            chat_completion(client, model=REASONING_MODELS[0], messages=[], max_tokens=100)


class TestChoosingAModel:
    def test_the_heavier_jobs_get_the_better_model(self):
        assert get_reasoning_model() == REASONING_MODELS[0]
        assert get_openai_model() == EVERYDAY_MODELS[0]

    def test_a_model_named_in_the_environment_wins(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
        assert get_openai_model() == "gpt-5.4"

    def test_a_named_model_still_has_something_to_fall_back_on(self, monkeypatch):
        monkeypatch.setenv("OPENAI_PARSING_MODEL", "gpt-5.5")
        client, calls = _client(Exception("insufficient_quota"))

        chat_completion(client, model=get_reasoning_model(), messages=[], max_tokens=100)

        assert calls[0]["model"] == "gpt-5.5"
        assert len(calls) == 2

    def test_nonsense_in_the_environment_is_ignored(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "claude-3")
        assert get_openai_model() == EVERYDAY_MODELS[0]

    def test_an_unrecognised_new_model_is_accepted(self, monkeypatch):
        """A name we have never heard of should not be downgraded on sight."""
        monkeypatch.setenv("OPENAI_MODEL", "gpt-7-supreme")
        assert get_openai_model() == "gpt-7-supreme"
