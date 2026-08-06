"""
Tests for correcting a child's record.

Three things have to hold. Taking one piece of work off the record must remove
exactly that piece and nothing else. Putting a mark right must change the
figures without leaving a second copy behind. And work the app could not mark
must never arrive as nought, because a zero nobody meant is worse than no score
at all.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pytest

from my_revision_helper.services import work as work_service


# ---------------------------------------------------------------------------
# Units: deciding whether a mark can be believed
# ---------------------------------------------------------------------------


@dataclass
class FakeQuestionMark:
    verdict: str


@dataclass
class FakeResult:
    marks_awarded: float = 0
    marks_available: float = 0
    percentage: Optional[float] = None
    overall_feedback: Optional[str] = None
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    weak_topics: List[str] = field(default_factory=list)
    question_marks: List[FakeQuestionMark] = field(default_factory=list)
    model: Optional[str] = None


def _verdicts(*verdicts: str) -> List[FakeQuestionMark]:
    return [FakeQuestionMark(v) for v in verdicts]


@pytest.mark.unit
class TestWhenAMarkShouldNotBeBelieved:
    def test_a_paper_out_of_nothing_makes_no_sense(self):
        assert work_service.unbelievable(FakeResult(marks_available=0)) is not None

    def test_finding_no_answer_anywhere_means_the_scan_failed(self):
        """A child who hands in a paper attempted some of it."""
        result = FakeResult(
            marks_available=10,
            percentage=0.0,
            question_marks=_verdicts("not_attempted", "not_attempted", "not_attempted"),
        )

        reason = work_service.unbelievable(result)
        assert reason is not None
        assert "no answers" in reason.lower()

    def test_mostly_blank_is_treated_the_same_way(self):
        result = FakeResult(
            marks_available=10,
            percentage=20.0,
            question_marks=_verdicts(
                "correct", "not_attempted", "not_attempted", "not_attempted", "not_attempted"
            ),
        )

        assert work_service.unbelievable(result) is not None

    def test_a_genuinely_poor_paper_is_still_a_real_mark(self):
        """Getting things wrong is not the same as not being read."""
        result = FakeResult(
            marks_awarded=2,
            marks_available=10,
            percentage=20.0,
            question_marks=_verdicts("incorrect", "incorrect", "partial", "correct", "incorrect"),
        )

        assert work_service.unbelievable(result) is None

    def test_a_good_paper_passes(self):
        result = FakeResult(
            marks_awarded=9,
            marks_available=10,
            percentage=90.0,
            question_marks=_verdicts("correct", "correct", "partial"),
        )

        assert work_service.unbelievable(result) is None

    def test_a_whole_paper_mark_with_a_score_is_accepted(self):
        """Marked as a whole, so there are no per-question verdicts to weigh."""
        result = FakeResult(marks_awarded=15, marks_available=20, percentage=75.0)

        assert work_service.unbelievable(result) is None

    def test_a_whole_paper_mark_with_nothing_found_is_not(self):
        result = FakeResult(marks_awarded=0, marks_available=20, percentage=0.0)

        assert work_service.unbelievable(result) is not None


@pytest.mark.unit
class TestWhichMarksCountTowardsTheAverage:
    def _marking(self, **fields):
        from my_revision_helper.models_db import Marking

        return Marking(**fields)

    def test_an_ordinary_mark_counts(self):
        marking = self._marking(percentage=72.0, status="marked", deleted_at=None)
        assert work_service.counts_towards_average(marking)

    def test_work_waiting_for_review_does_not(self):
        marking = self._marking(percentage=None, status="needs_review", deleted_at=None)
        assert not work_service.counts_towards_average(marking)

    def test_work_taken_off_the_record_does_not(self):
        marking = self._marking(
            percentage=72.0, status="marked", deleted_at=datetime(2026, 8, 1)
        )
        assert not work_service.counts_towards_average(marking)


@pytest.mark.unit
class TestRecognisingTheSameWorkTwice:
    def test_the_same_upload_has_the_same_fingerprint(self):
        first = work_service.content_digest(file_contents=[b"page one"], text="hello")
        second = work_service.content_digest(file_contents=[b"page one"], text="hello")

        assert first == second

    def test_different_work_does_not(self):
        first = work_service.content_digest(file_contents=[b"page one"], text="")
        second = work_service.content_digest(file_contents=[b"page two"], text="")

        assert first != second

    def test_surrounding_whitespace_is_not_a_difference(self):
        first = work_service.content_digest(file_contents=[], text="my answers")
        second = work_service.content_digest(file_contents=[], text="  my answers\n")

        assert first == second


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


def _requires_db():
    from my_revision_helper.database import engine

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - correcting work requires a database")
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
    response = client.post("/api/children", json={"name": "Work Child", "yearGroup": "Year 9"})
    assert response.status_code == 201
    return response.json()["id"]


def _record(client, child, *, title, awarded, available, subject="Mathematics", done_on=None):
    """Put a marked paper on the record the way a parent would."""
    data = {
        "childId": child,
        "subject": subject,
        "title": title,
        "marksAwarded": awarded,
        "marksAvailable": available,
    }
    if done_on:
        data["doneOn"] = done_on

    response = client.post("/api/handins", data=data)
    assert response.status_code == 201, response.text
    return response.json()


def _average(client, child):
    return client.get(f"/api/children/{child}/progress").json()["averagePercentage"]


@pytest.mark.integration
class TestTakingOnePieceOfWorkOffTheRecord:
    def test_only_that_piece_goes(self, client, child):
        keep = _record(client, child, title="Algebra", awarded=18, available=20)
        drop = _record(client, child, title="Mis-marked paper", awarded=0, available=20)

        response = client.delete(f"/api/work/{drop['assignmentId']}")
        assert response.status_code == 200

        remaining = client.get(f"/api/work?childId={child}").json()["items"]
        titles = [item["title"] for item in remaining]
        assert "Algebra" in titles
        assert "Mis-marked paper" not in titles
        assert keep["assignmentId"] in [item["id"] for item in remaining]

    def test_the_average_recovers_immediately(self, client, child):
        _record(client, child, title="Algebra", awarded=18, available=20)
        wrong = _record(client, child, title="Mis-marked paper", awarded=0, available=20)

        assert _average(client, child) == 45.0  # (90 + 0) / 2

        client.delete(f"/api/work/{wrong['assignmentId']}")

        assert _average(client, child) == 90.0

    def test_the_work_done_count_drops_by_one(self, client, child):
        _record(client, child, title="Algebra", awarded=18, available=20)
        before = client.get(f"/api/children/{child}/progress").json()["assignmentsDone"]

        wrong = _record(client, child, title="Wrong", awarded=1, available=20)
        client.delete(f"/api/work/{wrong['assignmentId']}")

        after = client.get(f"/api/children/{child}/progress").json()["assignmentsDone"]
        assert after == before

    def test_it_leaves_the_score_chart(self, client, child):
        wrong = _record(client, child, title="Wrong", awarded=2, available=20)

        client.delete(f"/api/work/{wrong['assignmentId']}")

        chart = client.get(f"/api/children/{child}/score-log").json()
        assert "Wrong" not in [entry["label"] for entry in chart]

    def test_it_can_be_put_back(self, client, child):
        work = _record(client, child, title="Deleted by mistake", awarded=14, available=20)
        client.delete(f"/api/work/{work['assignmentId']}")

        response = client.post(f"/api/work/{work['assignmentId']}/restore")
        assert response.status_code == 200

        titles = [i["title"] for i in client.get(f"/api/work?childId={child}").json()["items"]]
        assert "Deleted by mistake" in titles
        assert _average(client, child) == 70.0

    def test_deleting_twice_is_refused_rather_than_silently_ignored(self, client, child):
        work = _record(client, child, title="Once", awarded=10, available=20)
        client.delete(f"/api/work/{work['assignmentId']}")

        assert client.delete(f"/api/work/{work['assignmentId']}").status_code == 409

    def test_work_belonging_to_nobody_is_not_found(self, client, child):
        assert client.delete("/api/work/no-such-work").status_code == 404


@pytest.mark.integration
class TestPuttingAMarkRight:
    def test_the_new_score_sticks(self, client, child):
        """The auto-marker said 42% on work that was nearer 82%."""
        work = _record(client, child, title="Comprehension", awarded=21, available=50)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"marksAwarded": 41}
        )
        assert response.status_code == 200
        assert response.json()["percentage"] == 82.0

    def test_it_does_not_leave_a_second_copy(self, client, child):
        work = _record(client, child, title="Comprehension", awarded=21, available=50)

        client.patch(f"/api/work/{work['assignmentId']}", json={"marksAwarded": 41})

        items = client.get(f"/api/work?childId={child}").json()["items"]
        assert [i["title"] for i in items].count("Comprehension") == 1

    def test_the_average_follows(self, client, child):
        work = _record(client, child, title="Comprehension", awarded=25, available=50)
        assert _average(client, child) == 50.0

        client.patch(f"/api/work/{work['assignmentId']}", json={"marksAwarded": 45})

        assert _average(client, child) == 90.0

    def test_the_chart_follows_too(self, client, child):
        work = _record(client, child, title="Comprehension", awarded=25, available=50)

        client.patch(f"/api/work/{work['assignmentId']}", json={"marksAwarded": 45})

        chart = client.get(f"/api/children/{child}/score-log").json()
        entry = next(e for e in chart if e["label"] == "Comprehension")
        assert entry["scorePct"] == 90.0

    def test_the_total_can_be_corrected_as_well(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=18, available=20)

        response = client.patch(
            f"/api/work/{work['assignmentId']}",
            json={"marksAwarded": 18, "marksAvailable": 25},
        )
        assert response.json()["percentage"] == 72.0

    def test_the_title_and_subject_can_be_fixed(self, client, child):
        work = _record(client, child, title="Untitled", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}",
            json={"title": "Week 3 arithmetic", "subject": "Maths"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Week 3 arithmetic"
        assert body["subject"] == "Mathematics"  # Normalised on the way in

    def test_the_time_spent_can_be_corrected(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"minutesSpent": 55}
        )
        assert response.status_code == 200
        assert response.json()["minutesSpent"] == 55

    def test_corrected_time_reaches_the_weekly_total(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)
        before = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]

        client.patch(f"/api/work/{work['assignmentId']}", json={"minutesSpent": 55})

        after = client.get(f"/api/children/{child}/progress").json()["minutesLoggedThisWeek"]
        assert after == before + 55

    def test_negative_time_is_refused(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"minutesSpent": -5}
        )
        assert response.status_code == 400

    def test_a_note_can_be_added_after_the_fact(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"note": "Did this one twice"}
        )
        assert response.json()["note"] == "Did this one twice"

    def test_the_date_can_be_moved(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"doneOn": "2026-07-14"}
        )
        assert response.json()["doneOn"].startswith("2026-07-14")

    def test_a_score_above_the_total_is_refused(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"marksAwarded": 12}
        )
        assert response.status_code == 400
        assert "more than the total" in response.json()["detail"]

    def test_a_negative_score_is_refused(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"marksAwarded": -1}
        )
        assert response.status_code == 400

    def test_an_empty_title_is_refused(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(f"/api/work/{work['assignmentId']}", json={"title": "   "})
        assert response.status_code == 400

    def test_a_hand_entered_mark_is_credited_to_the_parent(self, client, child):
        work = _record(client, child, title="Paper 1", awarded=8, available=10)

        response = client.patch(
            f"/api/work/{work['assignmentId']}", json={"marksAwarded": 9}
        )
        assert response.json()["markedBy"] == "parent"


@pytest.mark.integration
class TestMovingWorkToTheRightChild:
    @pytest.fixture
    def sibling(self, client):
        response = client.post(
            "/api/children", json={"name": "Sibling", "yearGroup": "Year 7"}
        )
        return response.json()["id"]

    def test_it_lands_on_the_other_child(self, client, child, sibling):
        work = _record(client, child, title="Their brother's paper", awarded=16, available=20)

        response = client.post(
            f"/api/work/{work['assignmentId']}/move", json={"toChildId": sibling}
        )
        assert response.status_code == 200
        assert response.json()["childId"] == sibling

        titles = [i["title"] for i in client.get(f"/api/work?childId={sibling}").json()["items"]]
        assert "Their brother's paper" in titles

    def test_both_averages_are_worked_out_again(self, client, child, sibling):
        _record(client, child, title="Own work", awarded=10, available=20)
        misfiled = _record(client, child, title="Not theirs", awarded=20, available=20)

        assert _average(client, child) == 75.0

        client.post(f"/api/work/{misfiled['assignmentId']}/move", json={"toChildId": sibling})

        assert _average(client, child) == 50.0
        assert _average(client, sibling) == 100.0

    def test_moving_work_to_the_child_who_already_has_it_is_refused(self, client, child):
        work = _record(client, child, title="Paper", awarded=10, available=20)

        response = client.post(
            f"/api/work/{work['assignmentId']}/move", json={"toChildId": child}
        )
        assert response.status_code == 400

    def test_an_unknown_child_is_not_found(self, client, child):
        work = _record(client, child, title="Paper", awarded=10, available=20)

        response = client.post(
            f"/api/work/{work['assignmentId']}/move", json={"toChildId": "nobody"}
        )
        assert response.status_code == 404


@pytest.mark.integration
class TestWorkTheAppCouldNotMark:
    def _park(self, client, child, title="Unreadable scan"):
        """Record a piece of work the marker could not make sense of."""
        from my_revision_helper.database import SessionLocal
        from my_revision_helper.models_db import Marking, Submission

        work = _record(client, child, title=title, awarded=0, available=20)

        db = SessionLocal()
        try:
            submission = (
                db.query(Submission).filter(Submission.id == work["submissionId"]).first()
            )
            marking = (
                db.query(Marking).filter(Marking.submission_id == submission.id).first()
            )
            work_service.needs_review(db, marking, reason="The writing could not be read.")
            work_service.recompute_mastery(db, child)
            db.commit()
        finally:
            db.close()

        return work

    def test_it_stays_out_of_the_average(self, client, child):
        _record(client, child, title="Real paper", awarded=18, available=20)
        self._park(client, child)

        # 90%, not 45%: the unreadable scan is not a zero.
        assert _average(client, child) == 90.0

    def test_it_is_counted_so_it_cannot_be_missed(self, client, child):
        self._park(client, child)

        progress = client.get(f"/api/children/{child}/progress").json()
        assert progress["needsReviewCount"] == 1

    def test_it_says_why_it_needs_a_look(self, client, child):
        self._park(client, child)

        items = client.get(f"/api/work?childId={child}&needsReviewOnly=true").json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "needs_review"
        assert "could not be read" in items[0]["reviewReason"]

    def test_it_leaves_the_chart_until_someone_scores_it(self, client, child):
        self._park(client, child, title="Unreadable scan")

        chart = client.get(f"/api/children/{child}/score-log").json()
        assert "Unreadable scan" not in [e["label"] for e in chart]

    def test_marking_it_by_hand_makes_it_count(self, client, child):
        work = self._park(client, child, title="Unreadable scan")

        response = client.patch(
            f"/api/work/{work['assignmentId']}",
            json={"marksAwarded": 17, "marksAvailable": 20},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "marked"

        assert _average(client, child) == 85.0

        chart = client.get(f"/api/children/{child}/score-log").json()
        entry = next(e for e in chart if e["label"] == "Unreadable scan")
        assert entry["scorePct"] == 85.0

    def test_it_still_counts_as_work_done(self, client, child):
        """The child did the paper, whatever the app made of it."""
        before = client.get(f"/api/children/{child}/progress").json()["assignmentsDone"]

        self._park(client, child)

        after = client.get(f"/api/children/{child}/progress").json()["assignmentsDone"]
        assert after == before + 1


# ---------------------------------------------------------------------------
# What the charts are given to draw
# ---------------------------------------------------------------------------


def _subjects(client, child):
    rollup = client.get(f"/api/children/{child}/progress").json()["subjects"]
    return {row["subject"]: row for row in rollup}


@pytest.mark.integration
class TestSubjectsAChildHasActuallyWorkedIn:
    """
    The rollup used to come only from configured subjects, so work handed in by
    script showed a full record of marks beside an empty subject chart.
    """

    def test_a_subject_appears_once_there_is_work_in_it(self, client, child):
        _record(client, child, title="Atoms", awarded=8, available=10, subject="Chemistry")

        assert "Chemistry" in _subjects(client, child)

    def test_it_carries_the_average_across_that_subject(self, client, child):
        _record(client, child, title="Paper one", awarded=9, available=10, subject="Physics")
        _record(client, child, title="Paper two", awarded=7, available=10, subject="Physics")

        assert _subjects(client, child)["Physics"]["averageScore"] == 80.0

    def test_it_says_how_many_results_the_average_rests_on(self, client, child):
        _record(client, child, title="Only one", awarded=9, available=10, subject="Biology")

        assert _subjects(client, child)["Biology"]["markedCount"] == 1

    def test_subjects_stay_apart(self, client, child):
        _record(client, child, title="Maths", awarded=10, available=10, subject="Mathematics")
        _record(client, child, title="English", awarded=5, available=10, subject="English")

        rows = _subjects(client, child)
        assert rows["Mathematics"]["averageScore"] == 100.0
        assert rows["English"]["averageScore"] == 50.0

    def test_work_taken_off_the_record_stops_counting(self, client, child):
        _record(client, child, title="Good", awarded=9, available=10, subject="Chemistry")
        wrong = _record(client, child, title="Wrong", awarded=1, available=10, subject="Chemistry")

        client.delete(f"/api/work/{wrong['assignmentId']}")

        row = _subjects(client, child)["Chemistry"]
        assert row["averageScore"] == 90.0
        assert row["markedCount"] == 1


@pytest.mark.integration
class TestWhenAResultLandsOnTheChart:
    """
    The chart is a record of when work was done. A fortnight of paper
    worksheets caught up on one evening used to stack on that evening, which
    made the trend line meaningless just when it was most wanted.
    """

    def _chart(self, client, child):
        return client.get(f"/api/children/{child}/score-log").json()

    def test_it_lands_on_the_day_the_work_was_done(self, client, child):
        _record(client, child, title="Old paper", awarded=8, available=10, done_on="2026-07-14")

        entry = next(e for e in self._chart(client, child) if e["label"] == "Old paper")
        assert entry["recordedAt"].startswith("2026-07-14")

    def test_a_backlog_spreads_out_rather_than_stacking(self, client, child):
        for day in ("2026-07-14", "2026-07-16", "2026-07-18"):
            _record(client, child, title=f"Paper {day}", awarded=8, available=10, done_on=day)

        days = {e["recordedAt"][:10] for e in self._chart(client, child)}
        assert days == {"2026-07-14", "2026-07-16", "2026-07-18"}

    def test_correcting_the_date_moves_the_point(self, client, child):
        work = _record(client, child, title="Wrong day", awarded=8, available=10, done_on="2026-07-14")

        response = client.patch(f"/api/work/{work['assignmentId']}", json={"doneOn": "2026-07-02"})
        assert response.status_code == 200

        entry = next(e for e in self._chart(client, child) if e["label"] == "Wrong day")
        assert entry["recordedAt"].startswith("2026-07-02")

    def test_correcting_the_title_renames_the_point(self, client, child):
        work = _record(client, child, title="Untitled", awarded=8, available=10)

        client.patch(f"/api/work/{work['assignmentId']}", json={"title": "Trigonometry"})

        labels = [e["label"] for e in self._chart(client, child)]
        assert "Trigonometry" in labels
        assert "Untitled" not in labels
