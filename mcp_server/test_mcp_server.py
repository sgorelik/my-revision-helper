"""
Tests for the MCP server.

The tools are what an assistant drives without anyone watching closely, so what
matters is that vague input resolves sensibly, and that anything left out or
refused is said plainly rather than swallowed.

Run from the repository root with the MCP virtualenv:
    mcp_server/.venv/bin/python -m pytest mcp_server/test_mcp_server.py
"""

from pathlib import Path

import pytest

from mcp_server.api import ApiError, RevisionHelper
from mcp_server.files import collect_files, describe_skipped


# ---------------------------------------------------------------------------
# Working out which files were meant
# ---------------------------------------------------------------------------


@pytest.fixture
def papers(tmp_path: Path) -> Path:
    (tmp_path / "Maths_Week1.pdf").write_bytes(b"%PDF-1.4 maths")
    (tmp_path / "Physics_Week1.docx").write_bytes(b"docx bytes")
    (tmp_path / "notes.txt").write_text("some notes")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff jpeg")
    (tmp_path / "archive.zip").write_bytes(b"PK zip")
    (tmp_path / "empty.pdf").write_bytes(b"")
    nested = tmp_path / "week2"
    nested.mkdir()
    (nested / "Chemistry_Week2.pdf").write_bytes(b"%PDF-1.4 chemistry")
    return tmp_path


class TestCollectingFiles:
    def test_a_folder_brings_everything_readable_in_it(self, papers):
        collected = collect_files([str(papers)])

        names = [path.name for path in collected.files]
        assert "Maths_Week1.pdf" in names
        assert "Physics_Week1.docx" in names
        assert "notes.txt" in names
        assert "photo.jpg" in names

    def test_a_folder_is_searched_right_through(self, papers):
        collected = collect_files([str(papers)])

        assert "Chemistry_Week2.pdf" in [path.name for path in collected.files]

    def test_a_pattern_narrows_it_down(self, papers):
        collected = collect_files([f"{papers}/*.pdf"])

        assert [path.name for path in collected.files] == ["Maths_Week1.pdf"]

    def test_a_single_file_is_taken_as_given(self, papers):
        collected = collect_files([str(papers / "notes.txt")])

        assert len(collected.files) == 1

    def test_the_same_file_named_twice_is_only_sent_once(self, papers):
        target = str(papers / "Maths_Week1.pdf")
        collected = collect_files([target, target, str(papers)])

        assert [path.name for path in collected.files].count("Maths_Week1.pdf") == 1

    def test_the_order_does_not_change_between_calls(self, papers):
        first = collect_files([str(papers)]).files
        second = collect_files([str(papers)]).files

        assert first == second

    def test_something_the_app_cannot_read_is_left_out_with_a_reason(self, papers):
        collected = collect_files([str(papers)])

        assert "archive.zip" not in [path.name for path in collected.files]
        assert any("archive.zip" in reason for reason in collected.skipped)

    def test_an_empty_file_is_left_out(self, papers):
        collected = collect_files([str(papers)])

        assert "empty.pdf" not in [path.name for path in collected.files]
        assert any("empty" in reason.lower() for reason in collected.skipped)

    def test_a_path_that_matches_nothing_says_so(self):
        collected = collect_files(["/no/such/folder/at/all.pdf"])

        assert collected.is_empty
        assert collected.skipped

    def test_a_home_relative_path_is_understood(self):
        """Assistants write ~/Downloads far more often than the full path."""
        collected = collect_files(["~/definitely-not-here-9284.pdf"])

        assert "~" not in " ".join(collected.skipped)

    def test_too_many_at_once_is_capped_and_explained(self, papers):
        collected = collect_files([str(papers)], limit=2)

        assert len(collected.files) == 2
        assert any("limit" in reason for reason in collected.skipped)

    def test_what_was_left_out_reads_as_a_list(self, papers):
        described = describe_skipped(collect_files([str(papers)]))

        assert "Left out" in described
        assert "archive.zip" in described


# ---------------------------------------------------------------------------
# Talking to the API
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.reason = "Fake"
        self.content = b"x" if payload is not None or text else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class TestTheApiWrapper:
    def test_the_token_is_presented_as_a_bearer(self, monkeypatch):
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs)
            seen["url"] = url
            return FakeResponse(payload={"items": []})

        monkeypatch.setattr("mcp_server.api.requests.request", fake_request)
        RevisionHelper(base_url="https://example.test", token="secret-token").children()

        assert seen["headers"]["Authorization"] == "Bearer secret-token"
        assert seen["url"] == "https://example.test/api/children"

    def test_no_token_means_no_header_rather_than_an_empty_one(self, monkeypatch):
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs)
            return FakeResponse(payload={"items": []})

        monkeypatch.setattr("mcp_server.api.requests.request", fake_request)
        RevisionHelper(base_url="https://example.test", token="").children()

        assert "Authorization" not in seen["headers"]

    def test_the_servers_own_words_come_back(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_server.api.requests.request",
            lambda *a, **k: FakeResponse(400, {"detail": "A subject is needed"}),
        )

        with pytest.raises(ApiError, match="A subject is needed"):
            RevisionHelper(base_url="https://example.test", token="t").children()

    def test_a_validation_error_is_flattened_into_something_readable(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_server.api.requests.request",
            lambda *a, **k: FakeResponse(422, {"detail": [{"msg": "field required"}]}),
        )

        with pytest.raises(ApiError, match="field required"):
            RevisionHelper(base_url="https://example.test", token="t").children()

    def test_a_timeout_suggests_what_to_do_about_it(self, monkeypatch):
        import requests as real_requests

        def timeout(*a, **k):
            raise real_requests.Timeout()

        monkeypatch.setattr("mcp_server.api.requests.request", timeout)

        with pytest.raises(ApiError, match="fewer files"):
            RevisionHelper(base_url="https://example.test", token="t").children()


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------

CHILDREN = [
    {"id": "child-1", "name": "Yuri", "yearGroup": "Year 10"},
    {"id": "child-2", "name": "Savva", "yearGroup": "Year 8"},
]


class StubApi:
    """Stands in for the deployed app."""

    base_url = "https://example.test"
    token = "a-token"

    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def whoami(self):
        return self.responses.get("whoami", {"authenticated": True, "user_id": "auth0|me"})

    def children(self):
        return self.responses.get("children", CHILDREN)

    def papers(self, subject="", limit=100):
        return self.responses.get("papers", [])

    def progress(self, child_id):
        self.calls.append(("progress", child_id))
        return self.responses.get("progress", {})

    def upload_papers(self, files, **kwargs):
        self.calls.append(("upload", [f.name for f in files], kwargs))
        return self.responses.get(
            "upload",
            {
                "items": [
                    {
                        "filename": f.name,
                        "status": "ok",
                        "paper": {"title": f.stem, "questionCount": 5, "hasAnswerKey": True},
                    }
                    for f in files
                ]
            },
        )

    def hand_in(self, **kwargs):
        self.calls.append(("handin", kwargs))
        return self.responses.get(
            "handin",
            {
                "title": kwargs.get("title") or "Some work",
                "savedToLibrary": False,
                "questionCount": 0,
                "marking": None,
            },
        )

    def assign(self, **kwargs):
        self.calls.append(("assign", kwargs))
        return {}


@pytest.fixture
def stub(monkeypatch):
    """Point every tool at a stub instead of the network."""
    holder = {}

    def use(api):
        holder["api"] = api
        monkeypatch.setattr("mcp_server.server._api", lambda: api)
        return api

    return use


class TestWorkingOutWhoIsMeant:
    def test_a_name_is_enough(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        assert _resolve_child(api, "Yuri")["id"] == "child-1"

    def test_the_case_does_not_matter(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        assert _resolve_child(api, "yuri")["id"] == "child-1"

    def test_an_id_works_too(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        assert _resolve_child(api, "child-2")["name"] == "Savva"

    def test_part_of_a_name_is_enough_when_it_is_unambiguous(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        assert _resolve_child(api, "sav")["id"] == "child-2"

    def test_an_unknown_name_lists_the_real_ones(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        with pytest.raises(ApiError) as caught:
            _resolve_child(api, "Nobody")

        assert "Yuri" in str(caught.value) and "Savva" in str(caught.value)

    def test_saying_nothing_is_fine_when_there_is_only_one_child(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi(children=[CHILDREN[0]]))
        assert _resolve_child(api, "")["name"] == "Yuri"

    def test_saying_nothing_asks_which_one_when_there_are_two(self, stub):
        from mcp_server.server import _resolve_child

        api = stub(StubApi())
        with pytest.raises(ApiError, match="which child"):
            _resolve_child(api, "")


class TestUploadingPapers:
    def test_it_reports_what_landed(self, stub, papers):
        from mcp_server.server import upload_papers

        stub(StubApi())
        out = upload_papers([f"{papers}/*.pdf"], subject="Mathematics")

        assert "Added 1 paper" in out
        assert "Maths_Week1" in out
        assert "5 questions" in out

    def test_a_file_the_server_rejects_is_named(self, stub, papers):
        from mcp_server.server import upload_papers

        stub(
            StubApi(
                upload={
                    "items": [
                        {"filename": "Maths_Week1.pdf", "status": "failed", "error": "Unreadable"}
                    ]
                }
            )
        )
        out = upload_papers([f"{papers}/Maths_Week1.pdf"])

        assert "1 failed" in out
        assert "Unreadable" in out

    def test_files_it_could_not_send_are_listed_too(self, stub, papers):
        from mcp_server.server import upload_papers

        stub(StubApi())
        out = upload_papers([str(papers)])

        assert "archive.zip" in out

    def test_nothing_to_send_says_so_rather_than_calling_the_server(self, stub):
        from mcp_server.server import upload_papers

        api = stub(StubApi())
        out = upload_papers(["/nowhere/at/all/*.pdf"])

        assert "Nothing to upload" in out
        assert api.calls == []

    def test_the_subject_is_passed_through(self, stub, papers):
        from mcp_server.server import upload_papers

        api = stub(StubApi())
        upload_papers([f"{papers}/*.pdf"], subject="Physics", week_label="Week 1")

        _, _, kwargs = api.calls[0]
        assert kwargs["subject"] == "Physics"
        assert kwargs["week_label"] == "Week 1"


class TestHandingWorkIn:
    def test_work_with_no_scan_is_recorded(self, stub):
        from mcp_server.server import hand_in_work

        api = stub(StubApi())
        out = hand_in_work("Yuri", "Mathematics", minutes_spent=40, title="Fractions")

        assert "Recorded" in out
        assert "Counted as done" in out
        assert api.calls[0][1]["child_id"] == "child-1"

    def test_a_marked_scan_reports_the_score(self, stub, papers):
        from mcp_server.server import hand_in_work

        stub(
            StubApi(
                handin={
                    "title": "Fractions worksheet",
                    "savedToLibrary": True,
                    "questionCount": 12,
                    "marking": {
                        "marksAwarded": 18,
                        "marksAvailable": 25,
                        "percentage": 72.0,
                        "markedBy": "ai",
                        "weakTopics": ["percentages"],
                    },
                }
            )
        )
        out = hand_in_work("Yuri", "Mathematics", paths=[f"{papers}/*.pdf"])

        assert "18/25" in out and "72.0%" in out
        assert "percentages" in out
        assert "12 questions" in out

    def test_it_says_when_you_marked_it_rather_than_the_app(self, stub):
        from mcp_server.server import hand_in_work

        stub(
            StubApi(
                handin={
                    "title": "Past paper",
                    "savedToLibrary": False,
                    "questionCount": 0,
                    "marking": {
                        "marksAwarded": 18,
                        "marksAvailable": 25,
                        "percentage": 72.0,
                        "markedBy": "parent",
                        "weakTopics": [],
                    },
                }
            )
        )
        out = hand_in_work("Yuri", "Mathematics", marks_awarded=18, marks_available=25)

        assert "by you" in out

    def test_an_unknown_child_fails_before_anything_is_sent(self, stub):
        from mcp_server.server import hand_in_work

        api = stub(StubApi())
        out = hand_in_work("Nobody", "Mathematics", minutes_spent=30)

        assert out.startswith("Failed")
        assert not any(call[0] == "handin" for call in api.calls)

    def test_files_that_cannot_be_sent_stop_it_rather_than_silently_recording_nothing(self, stub):
        from mcp_server.server import hand_in_work

        api = stub(StubApi())
        out = hand_in_work("Yuri", "Mathematics", paths=["/nowhere/x.pdf"])

        assert "None of those files could be sent" in out
        assert not any(call[0] == "handin" for call in api.calls)


class TestAssigningWork:
    def test_a_task_needs_no_paper(self, stub):
        from mcp_server.server import assign_work

        api = stub(StubApi())
        out = assign_work("Yuri", title="Read two chapters", subject="English")

        assert "Assigned" in out
        assert api.calls[0][1]["paper_id"] is None

    def test_a_paper_is_found_by_title(self, stub):
        from mcp_server.server import assign_work

        api = stub(
            StubApi(papers=[{"id": "p1", "title": "Fractions worksheet", "subject": "Mathematics"}])
        )
        out = assign_work("Yuri", paper="fractions", scheduled_date="2026-08-10")

        assert api.calls[0][1]["paper_id"] == "p1"
        assert "2026-08-10" in out

    def test_an_ambiguous_paper_title_asks_rather_than_guesses(self, stub):
        from mcp_server.server import assign_work

        stub(
            StubApi(
                papers=[
                    {"id": "p1", "title": "Fractions week 1", "subject": "Mathematics"},
                    {"id": "p2", "title": "Fractions week 2", "subject": "Mathematics"},
                ]
            )
        )
        out = assign_work("Yuri", paper="fractions")

        assert out.startswith("Failed")
        assert "More than one" in out

    def test_nothing_to_assign_is_refused(self, stub):
        from mcp_server.server import assign_work

        stub(StubApi())
        assert assign_work("Yuri").startswith("Failed")


class TestCheckingTheSetup:
    def test_a_missing_token_is_the_first_thing_reported(self, monkeypatch):
        from mcp_server.server import check_connection

        class NoToken(StubApi):
            token = ""

        monkeypatch.setattr("mcp_server.server._api", lambda: NoToken())
        assert "No REVISION_HELPER_TOKEN" in check_connection()

    def test_a_rejected_token_explains_which_settings_to_look_at(self, stub):
        from mcp_server.server import check_connection

        stub(StubApi(whoami={"authenticated": False}))
        out = check_connection()

        assert "API_TOKEN" in out and "API_TOKEN_USER_ID" in out

    def test_a_working_setup_names_the_children(self, stub):
        from mcp_server.server import check_connection

        stub(StubApi())
        out = check_connection()

        assert "Connected" in out
        assert "Yuri" in out and "Savva" in out


class TestReadingProgress:
    def test_the_headline_numbers_come_back(self, stub):
        from mcp_server.server import get_progress

        stub(
            StubApi(
                progress={
                    "assignmentsDone": 12,
                    "assignmentsTotal": 20,
                    "assignmentsOverdue": 2,
                    "averagePercentage": 71.4,
                    "minutesLoggedThisWeek": 180,
                    "streakDays": 4,
                    "weakTopics": [{"topic": "index laws"}],
                    "subjects": [
                        {"subject": "Mathematics", "latestScore": 68, "gapToAverage": -8.0}
                    ],
                }
            )
        )
        out = get_progress("Yuri")

        assert "12/20" in out
        assert "2 overdue" in out
        assert "71%" in out
        assert "index laws" in out
        assert "Mathematics" in out and "-8" in out

    def test_a_single_day_streak_reads_as_one_day(self, stub):
        from mcp_server.server import get_progress

        stub(StubApi(progress={"streakDays": 1, "assignmentsDone": 1, "assignmentsTotal": 1}))

        assert "1 day" in get_progress("Yuri")
        assert "1 days" not in get_progress("Yuri")
