"""
Tests for handing in work that was never assigned.

Two paths matter here. Work that arrives as a scan carrying its own questions
should end up marked, with the blank paper kept for the other child and the
child's answers nowhere near it. Work that arrives with no scan at all should
still count towards the term's totals.
"""

import os
from datetime import datetime, timedelta

import pytest

from my_revision_helper.routers.handins import _day_done, _manual_result

# A worksheet done on paper: printed questions, answers written in by hand.
# Sent as .txt so no transcription is needed and the tags are exactly ours.
COMPLETED_WORKSHEET = """Mathematics — Fractions and percentages

1. Work out 3/4 of 60.
Answer: [written] 45  ......................... (2)

2. Increase £80 by 15%.
Answer: [written] 92  ......................... (2)

3. Write 0.375 as a fraction in its simplest form.
Answer: [written] 3/8  ......................... (2)

4. Work out 15% of 240.
Answer: [written] 36  ......................... (2)

5. A shirt costs £24 after a 20% discount. What was the original price?
Answer: [written] £30  ......................... (3)
"""


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTheDayTheWorkWasDone:
    def test_it_defaults_to_today(self):
        assert _day_done("").date() == datetime.now().date()

    def test_an_iso_date_is_taken_as_given(self):
        assert _day_done("2026-07-14") == datetime(2026, 7, 14, 0, 0)

    def test_the_time_of_day_is_dropped(self):
        """Nobody records the hour they finished a worksheet."""
        assert _day_done("2026-07-14T19:32:00Z") == datetime(2026, 7, 14, 0, 0)

    def test_nonsense_is_refused(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as caught:
            _day_done("last Tuesday")
        assert caught.value.status_code == 400


@pytest.mark.unit
class TestAScoreMarkedOnPaper:
    def test_it_becomes_a_percentage(self):
        result = _manual_result(marks_awarded=18, marks_available=25, note=None)

        assert result.percentage == 72.0
        assert result.marks_awarded == 18
        assert result.marks_available == 25

    def test_the_note_carries_through_as_the_feedback(self):
        result = _manual_result(marks_awarded=8, marks_available=10, note="Rushed the last one")

        assert result.overall_feedback == "Rushed the last one"

    def test_there_are_no_per_question_marks_to_invent(self):
        assert _manual_result(marks_awarded=8, marks_available=10, note=None).question_marks == []


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


def _requires_db():
    from my_revision_helper.database import engine

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - handing work in requires a database")
    if engine is None:
        pytest.skip("Database engine not configured")


@pytest.fixture
def client():
    _requires_db()

    from fastapi.testclient import TestClient

    from my_revision_helper.api import app
    from my_revision_helper.database import init_db

    init_db()
    return TestClient(app)


@pytest.fixture
def child(client):
    response = client.post("/api/children", json={"name": "Hand-in Child", "yearGroup": "Year 10"})
    assert response.status_code == 201
    return response.json()["id"]


def _hand_in(client, child, **fields):
    """Post a hand-in, with the fields every one of them needs filled in."""
    files = fields.pop("files", None)
    data = {"childId": child, "subject": "Mathematics", **fields}
    return client.post("/api/handins", data=data, files=files)


@pytest.mark.integration
class TestWorkThatWasNeverScanned:
    def test_it_is_recorded_as_done(self, client, child):
        response = _hand_in(
            client, child, title="Fractions worksheet", minutesSpent=35, note="Did it in the car"
        )
        assert response.status_code == 201

        body = response.json()
        assert body["assignmentId"]
        assert body["submissionId"]
        # Nothing was marked, so nothing pretends to have been.
        assert body["marking"] is None

    def test_it_shows_up_as_a_finished_assignment(self, client, child):
        before = client.get(f"/api/children/{child}/progress").json()["assignmentsDone"]

        _hand_in(client, child, title="Fractions worksheet", minutesSpent=35)

        after = client.get(f"/api/children/{child}/progress").json()
        assert after["assignmentsDone"] == before + 1

    def test_the_time_reaches_the_weekly_total(self, client, child):
        before = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]

        _hand_in(client, child, title="Reading", minutesSpent=40)

        after = client.get(f"/api/children/{child}/progress").json()
        assert after["minutesLoggedThisWeek"] == before + 40

    def test_it_does_not_sit_in_the_to_do_list(self, client, child):
        """Work already done must not come back as something still to do."""
        _hand_in(client, child, title="Fractions worksheet", minutesSpent=20)

        today = client.get(f"/api/children/{child}/today").json()
        titles = [item["title"] for item in today.get("dueToday", [])]
        assert "Fractions worksheet" not in titles

    def test_a_score_marked_on_paper_reaches_the_chart(self, client, child):
        response = _hand_in(
            client,
            child,
            title="Past paper 3",
            minutesSpent=60,
            marksAwarded=18,
            marksAvailable=25,
        )
        assert response.status_code == 201
        assert response.json()["marking"]["percentage"] == 72.0

        progress = client.get(f"/api/children/{child}/progress").json()
        assert any(entry["scorePct"] == 72.0 for entry in progress["scoreLog"])

    def test_a_hand_marked_score_says_who_marked_it(self, client, child):
        response = _hand_in(
            client, child, title="Past paper 3", marksAwarded=18, marksAvailable=25
        )

        assert response.json()["marking"]["markedBy"] == "parent"

    def test_work_dated_to_when_it_happened(self, client, child):
        """Otherwise last week's work lands in this week's totals."""
        last_week = (datetime.now() - timedelta(days=9)).date().isoformat()

        response = _hand_in(client, child, title="Old worksheet", minutesSpent=45, doneOn=last_week)
        assert response.status_code == 201

        this_week = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]
        assert this_week == 0

    def test_a_score_with_no_total_is_refused(self, client, child):
        response = _hand_in(client, child, title="Past paper", marksAwarded=18)

        assert response.status_code == 400
        assert "out of" in response.json()["detail"]

    def test_a_score_above_the_total_is_refused(self, client, child):
        response = _hand_in(client, child, title="Past paper", marksAwarded=30, marksAvailable=25)

        assert response.status_code == 400

    def test_an_empty_hand_in_is_refused(self, client, child):
        """No work, no score, no time: there is nothing to record."""
        response = _hand_in(client, child, title="Nothing at all")

        assert response.status_code == 400

    def test_a_subject_is_required(self, client, child):
        response = client.post(
            "/api/handins", data={"childId": child, "subject": "  ", "minutesSpent": 20}
        )

        assert response.status_code == 400

    def test_an_unknown_child_is_refused(self, client):
        response = client.post(
            "/api/handins",
            data={"childId": "nobody", "subject": "Mathematics", "minutesSpent": 20},
        )

        assert response.status_code == 404

    def test_another_account_cannot_hand_work_in_for_my_child(self, client, child):
        from fastapi.testclient import TestClient

        from my_revision_helper.api import app

        other = TestClient(app)  # a fresh session cookie is a different owner
        response = other.post(
            "/api/handins",
            data={"childId": child, "subject": "Mathematics", "minutesSpent": 20},
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestAScanTheAppCannotRead:
    """
    An empty file stands in for a photo too blurred to transcribe. Whatever the
    cause, the child did the work, and the app must not decide they scored
    nothing just because it could not see the answers.
    """

    def _blurred(self, client, child):
        response = _hand_in(
            client,
            child,
            title="Blurred photo",
            minutesSpent=30,
            files=[("files", ("blurred.txt", "   \n  \n", "text/plain"))],
        )
        assert response.status_code == 201, response.text
        return response

    def test_it_is_still_recorded_rather_than_refused(self, client, child):
        response = self._blurred(client, child)

        assert response.status_code == 201
        assert response.json()["assignmentId"]

    def test_it_carries_no_score(self, client, child):
        marking = self._blurred(client, child).json()["marking"]

        assert marking["status"] == "needs_review"
        assert marking["percentage"] is None
        assert marking["marksAwarded"] is None

    def test_it_says_what_to_do_about_it(self, client, child):
        marking = self._blurred(client, child).json()["marking"]

        assert "Enter the mark yourself" in marking["reviewReason"]

    def test_it_does_not_drag_the_average_down(self, client, child):
        _hand_in(client, child, title="A real paper", marksAwarded=18, marksAvailable=20)
        self._blurred(client, child)

        progress = client.get(f"/api/children/{child}/progress").json()
        assert progress["averagePercentage"] == 90.0
        assert progress["needsReviewCount"] == 1

    def test_the_time_spent_still_counts(self, client, child):
        before = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]

        self._blurred(client, child)

        after = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]
        assert after == before + 30


@pytest.mark.integration
class TestAScanThatCarriesItsOwnQuestions:
    """
    The scan has the questions printed on it and the answers written in, so it can
    become a paper in its own right. A score is passed in here so the marking
    model is not needed; what is under test is what gets kept.
    """

    def _hand_in_the_worksheet(self, client, child, **extra):
        return _hand_in(
            client,
            child,
            title="Fractions and percentages",
            minutesSpent=30,
            marksAwarded=9,
            marksAvailable=11,
            files=[("files", ("fractions.txt", COMPLETED_WORKSHEET, "text/plain"))],
            **extra,
        )

    def test_it_is_kept_as_a_paper_in_the_library(self, client, child):
        response = self._hand_in_the_worksheet(client, child)
        assert response.status_code == 201

        body = response.json()
        assert body["savedToLibrary"] is True
        assert body["paperId"]
        assert body["questionCount"] >= 4

    def _library_text(self, client, paper_id):
        """Everything on the library copy the next child would read."""
        paper = client.get(f"/api/papers/{paper_id}").json()
        parts = [paper.get("questionText") or "", paper.get("answerKeyText") or ""]
        parts += [q.get("questionText") or "" for q in paper.get("questions", [])]
        return "\n".join(parts)

    def test_the_library_copy_does_not_carry_the_childs_answers(self, client, child):
        """The point of keeping it is to hand it to the other child unspoiled."""
        paper_id = self._hand_in_the_worksheet(client, child).json()["paperId"]

        text = self._library_text(client, paper_id)

        assert "45" not in text
        assert "3/8" not in text
        assert "£30" not in text
        assert "[written]" not in text

    def test_the_library_copy_still_carries_the_questions(self, client, child):
        paper_id = self._hand_in_the_worksheet(client, child).json()["paperId"]

        text = self._library_text(client, paper_id)
        paper = client.get(f"/api/papers/{paper_id}").json()

        assert "Work out 3/4 of 60." in text
        assert "Increase £80 by 15%." in text
        assert paper["questionCount"] >= 4

    def test_the_answer_space_and_marks_survive_on_the_library_copy(self, client, child):
        """It has to be usable as a worksheet, not just a list of questions."""
        paper_id = self._hand_in_the_worksheet(client, child).json()["paperId"]

        text = self._library_text(client, paper_id)

        assert "Answer:" in text
        assert "(2)" in text

    def test_the_paper_has_no_answer_key_to_give_away(self, client, child):
        paper_id = self._hand_in_the_worksheet(client, child).json()["paperId"]

        detail = client.get(f"/api/papers/{paper_id}").json()

        assert not detail.get("hasAnswerKey")

    def test_the_work_itself_is_kept_with_the_answers_intact(self, client, child):
        """Stripping is for the library copy; the marking needs the real thing."""
        body = self._hand_in_the_worksheet(client, child).json()

        marking = client.get(f"/api/markings/{body['marking']['id']}").json()
        assert marking["percentage"] == pytest.approx(81.8, abs=0.1)

    def test_it_is_named_from_the_page_when_no_title_is_typed(self, client, child):
        """"Fractions and percentages" is more use later than "Mathematics work, 31 Jul"."""
        response = _hand_in(
            client,
            child,
            minutesSpent=30,
            marksAwarded=9,
            marksAvailable=11,
            files=[("files", ("fractions.txt", COMPLETED_WORKSHEET, "text/plain"))],
        )
        assert response.status_code == 201

        title = response.json()["title"]
        assert "work," not in title  # not the date-stamped fallback
        assert "ractions" in title or "ercentages" in title

    def test_a_typed_title_wins_over_the_page(self, client, child):
        response = self._hand_in_the_worksheet(client, child)

        assert response.json()["title"] == "Fractions and percentages"

    def test_not_saving_it_to_the_library_is_respected(self, client, child):
        response = self._hand_in_the_worksheet(client, child, saveToLibrary=False)

        body = response.json()
        assert body["savedToLibrary"] is False
        assert body["paperId"] is None

    def test_a_page_of_bare_answers_is_not_turned_into_a_paper(self, client, child):
        """There are no questions on it, so there is no worksheet to keep."""
        answers_only = "[written] 1. 45\n[written] 2. 92\n[written] 3. 3/8\n"

        response = _hand_in(
            client,
            child,
            title="Answers only",
            marksAwarded=2,
            marksAvailable=3,
            files=[("files", ("answers.txt", answers_only, "text/plain"))],
        )
        assert response.status_code == 201

        body = response.json()
        assert body["savedToLibrary"] is False
        # Still recorded as work done, even though it could not become a paper.
        assert body["marking"]["percentage"] == pytest.approx(66.7, abs=0.1)
