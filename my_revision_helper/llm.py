"""
Shared OpenAI client access.

Lives outside api.py so services and routers can reach the model without
importing the API module (which imports them in turn).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - SDK is optional at import time
    OpenAI = None  # type: ignore

# Preference order, best first. Each list is walked top down until one answers,
# so the app runs on the newest model the account can actually reach and drops
# to the next only when the API refuses. Being listed by /models is not the same
# as being usable: a tier the plan does not cover still appears there and only
# fails when called.
#
# Everyday work: reading a request, writing questions, short feedback.
EVERYDAY_MODELS = ["gpt-5.6-terra", "gpt-5.4", "gpt-4o-mini"]

# The heavier jobs, where being right matters more than being cheap: pulling a
# workbook apart into questions, marking a paper against its answer key, and
# reading a page of a child's handwriting.
REASONING_MODELS = ["gpt-5.6-sol", "gpt-5.5", "gpt-5.4", "gpt-4o"]

DEFAULT_MODEL = EVERYDAY_MODELS[0]
DEFAULT_REASONING_MODEL = REASONING_MODELS[0]

# Names are no longer a fixed list. A new model appears every few weeks, and a
# hardcoded allow-list quietly downgraded anything newer than itself back to the
# default, which is how this app was still on gpt-4o. Anything obviously wrong
# is rejected by the API on the first call instead.
_PLAUSIBLE_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")

# Models that still take the older parameter names. Everything from GPT-5
# onwards rejects `max_tokens` outright and refuses any temperature but its
# default, so the two generations cannot be called the same way.
_LEGACY_PARAM_PREFIXES = ("gpt-4", "gpt-3", "chatgpt-4")

# A newer model spends part of its budget thinking before it writes anything,
# and that thinking counts against the same ceiling. A limit tuned for gpt-4o
# can therefore be swallowed whole and return an empty string, so give those
# models more headroom. The ceiling only caps runaway replies; a short answer
# still costs what it costs.
_REASONING_HEADROOM = 4

# Headroom has a limit of its own: parsing a workbook already asks for 16k, and
# multiplying that blindly would ask for more than a model will emit.
_MAX_COMPLETION_TOKENS = 32000

# Learned at runtime when a model disagrees with the guesses above, so a family
# that changes the rules again costs one failed call rather than an outage.
_legacy_params: Dict[str, bool] = {}
_unavailable: set = set()


def get_openai_client() -> Optional[Any]:
    """Return an OpenAI client if the SDK and API key are available."""
    if OpenAI is None:
        logger.warning("OpenAI SDK not installed")
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY environment variable not set")
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to create OpenAI client: {e}", exc_info=True)
        return None


def _preference(env_var: str, ladder: List[str]) -> List[str]:
    """
    The models to try, best first.

    Naming one in the environment puts it at the front rather than replacing the
    ladder, so a deliberate choice is honoured while still leaving something to
    fall back on if that model is unreachable.
    """
    chosen = os.getenv(env_var)
    if not chosen:
        return list(ladder)

    chosen = chosen.strip()
    if not chosen.startswith(_PLAUSIBLE_PREFIXES):
        logger.warning(f"{env_var}='{chosen}' does not look like an OpenAI model; ignoring it")
        return list(ladder)

    return [chosen] + [m for m in ladder if m != chosen]


def get_openai_model() -> str:
    """The everyday model: the best one not yet known to be unreachable."""
    return next(
        (m for m in _preference("OPENAI_MODEL", EVERYDAY_MODELS) if m not in _unavailable),
        DEFAULT_MODEL,
    )


def get_reasoning_model() -> str:
    """
    Model used for the heavier structured tasks: parsing a workbook into
    questions, marking a completed paper against its answer key, and reading a
    page of handwriting.

    These run once per document rather than once per interaction, so the
    accuracy is worth more than the token cost.
    """
    return next(
        (m for m in _preference("OPENAI_PARSING_MODEL", REASONING_MODELS) if m not in _unavailable),
        DEFAULT_REASONING_MODEL,
    )


def _is_unreachable(error: Exception) -> bool:
    """
    Whether this model is one we should stop asking for, rather than retry.

    A plan that does not cover a tier, or a model that is not a chat model, will
    never succeed however long we wait. An ordinary rate limit will, so that one
    is left alone for the caller to retry.
    """
    message = str(error).lower()
    permanent = (
        "insufficient_quota",
        "does not exist",
        "not a chat model",
        "do not have access",
        "must be verified",
        "model_not_found",
    )
    return any(hint in message for hint in permanent)


def _uses_legacy_params(model: str) -> bool:
    """Whether this model wants `max_tokens` and accepts a chosen temperature."""
    if model in _legacy_params:
        return _legacy_params[model]
    return model.startswith(_LEGACY_PARAM_PREFIXES)


def _build_params(
    model: str,
    messages: Any,
    legacy: bool,
    temperature: Optional[float],
    max_tokens: Optional[int],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"model": model, "messages": messages, **extra}

    if max_tokens is not None:
        if legacy:
            params["max_tokens"] = max_tokens
        else:
            params["max_completion_tokens"] = min(
                max_tokens * _REASONING_HEADROOM, max(max_tokens, _MAX_COMPLETION_TOKENS)
            )

    # Newer models run at a fixed temperature and reject any request to change
    # it, including the zero we would like for marking.
    if legacy and temperature is not None:
        params["temperature"] = temperature

    return params


def _call_one(
    client: Any,
    model: str,
    messages: Any,
    temperature: Optional[float],
    max_tokens: Optional[int],
    extra: Dict[str, Any],
) -> Any:
    """
    One model, either dialect.

    GPT-4 era models take `max_tokens` and any temperature. GPT-5 era models
    take `max_completion_tokens` and refuse every temperature but their own
    default. If the guess is wrong the call is retried the other way round and
    the answer remembered, so an unfamiliar model costs one wasted request.
    """
    legacy = _uses_legacy_params(model)

    try:
        return client.chat.completions.create(
            **_build_params(model, messages, legacy, temperature, max_tokens, extra)
        )
    except Exception as e:
        message = str(e)
        wrong_dialect = any(
            hint in message for hint in ("max_tokens", "max_completion_tokens", "temperature")
        ) and "unsupported" in message.lower()
        if not wrong_dialect:
            raise

        logger.info(f"{model} wants the {'newer' if legacy else 'older'} parameter names; retrying")
        _legacy_params[model] = not legacy
        return client.chat.completions.create(
            **_build_params(model, messages, not legacy, temperature, max_tokens, extra)
        )


def chat_completion(
    client: Any,
    *,
    model: str,
    messages: Any,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **extra: Any,
) -> Any:
    """
    Call a chat model without caring which generation it belongs to, dropping to
    an older one if the preferred model is out of reach.

    Callers ask for what they want and this sorts out the dialect, so changing
    model is a config change rather than an edit to every call site. If the
    account cannot reach the requested model at all, the rest of its ladder is
    tried in turn and the dead model is not asked for again, which keeps marking
    working on the evening a new tier turns out not to be covered by the plan.
    """
    ladder = REASONING_MODELS if model in REASONING_MODELS else EVERYDAY_MODELS
    remaining = [m for m in [model] + ladder if m not in _unavailable]
    # Dedupe while keeping order, and never end up with nothing to call.
    remaining = list(dict.fromkeys(remaining)) or [model]

    last_error: Optional[Exception] = None
    for candidate in remaining:
        try:
            return _call_one(client, candidate, messages, temperature, max_tokens, extra)
        except Exception as e:
            if not _is_unreachable(e):
                raise

            logger.warning(f"Model {candidate} is not available to this account: {str(e)[:120]}")
            _unavailable.add(candidate)
            last_error = e

    assert last_error is not None
    raise last_error
