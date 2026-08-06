"""
Correcting the record: taking a piece of work back, or putting its mark right.

A marked paper is three rows — the assignment, the submission and the marking —
and they only make sense together, so they are taken off and put back together.
Nothing is actually deleted: a mis-marked paper needs to leave the average, not
leave the world, and the scan behind it is often the only copy.

Topic mastery is the awkward part. It accumulates as work is marked rather than
being derived, so it cannot be unwound by subtraction — an override may already
have changed the question marks it was built from. It is rebuilt from what is
still standing instead.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Query, Session

from ..models_db import (
    Assignment,
    Marking,
    QuestionMark,
    ScoreLogEntry,
    Submission,
    TopicMastery,
)

logger = logging.getLogger(__name__)

NEEDS_REVIEW = "needs_review"
MARKED = "marked"


def live(query: Query, model) -> Query:
    """Only rows that have not been taken off the record."""
    return query.filter(model.deleted_at.is_(None))


def counts_towards_average(marking: Marking) -> bool:
    """
    Whether a marking should move the child's average.

    Work waiting for a person to look at it has no percentage yet, and a score
    nobody believes is worse than no score.
    """
    return (
        marking.deleted_at is None
        and marking.status != NEEDS_REVIEW
        and marking.percentage is not None
    )


def content_digest(*, file_contents: Iterable[bytes], text: str = "") -> str:
    """
    A fingerprint of what was handed in.

    Lets a resend that followed a timeout recognise itself, rather than adding
    the same paper to the record twice.
    """
    digest = hashlib.sha256()
    for chunk in file_contents:
        digest.update(hashlib.sha256(chunk).digest())
    digest.update((text or "").strip().encode("utf-8"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Taking work off the record, and putting it back
# ---------------------------------------------------------------------------


def _related(db: Session, assignment: Assignment) -> Tuple[List[Submission], List[Marking]]:
    submissions = (
        db.query(Submission).filter(Submission.assignment_id == assignment.id).all()
    )
    markings = (
        db.query(Marking)
        .filter(Marking.submission_id.in_([s.id for s in submissions] or [""]))
        .all()
    )
    return submissions, markings


def soft_delete(db: Session, assignment: Assignment) -> None:
    """
    Take a piece of work off the lists and the totals, keeping it recoverable.

    The score log goes with it, or the chart would still show a mark for work
    that is no longer there.
    """
    when = datetime.utcnow()
    submissions, markings = _related(db, assignment)

    assignment.deleted_at = when
    for submission in submissions:
        submission.deleted_at = when
    for marking in markings:
        marking.deleted_at = when

    if markings:
        for entry in (
            db.query(ScoreLogEntry)
            .filter(ScoreLogEntry.marking_id.in_([m.id for m in markings]))
            .all()
        ):
            entry.deleted_at = when

    db.flush()
    recompute_mastery(db, assignment.child_id)
    logger.info(f"Took work {assignment.id} off {assignment.child_id}'s record")


def restore(db: Session, assignment: Assignment) -> None:
    """Put a piece of work back exactly as it was."""
    submissions, markings = _related(db, assignment)

    assignment.deleted_at = None
    for submission in submissions:
        submission.deleted_at = None
    for marking in markings:
        marking.deleted_at = None

    if markings:
        for entry in (
            db.query(ScoreLogEntry)
            .filter(ScoreLogEntry.marking_id.in_([m.id for m in markings]))
            .all()
        ):
            entry.deleted_at = None

    db.flush()
    recompute_mastery(db, assignment.child_id)


# ---------------------------------------------------------------------------
# Rebuilding what was accumulated
# ---------------------------------------------------------------------------

# Kept in step with marking_service, which sets these when work is first marked.
from .marking_service import SECURE_TOPIC_THRESHOLD, WEAK_TOPIC_THRESHOLD  # noqa: E402


def recompute_mastery(db: Session, child_id: str) -> None:
    """
    Rebuild a child's topic mastery from the work that still counts.

    Called after anything that changes which marks are real: a deletion, a
    restore, a corrected score, or work moving to another child. Rebuilding
    rather than adjusting is deliberate — the running totals cannot be trusted
    to reverse, because a parent's per-question override changes the marks
    underneath them without touching the total.
    """
    markings = (
        db.query(Marking)
        .filter(
            Marking.child_id == child_id,
            Marking.deleted_at.is_(None),
            Marking.status != NEEDS_REVIEW,
        )
        .all()
    )

    # (subject, topic) -> [attempts, awarded, available, last seen]
    totals: Dict[Tuple[str, str], List] = {}

    for marking in markings:
        question_marks = (
            db.query(QuestionMark).filter(QuestionMark.marking_id == marking.id).all()
        )

        if question_marks:
            per_topic: Dict[str, List[float]] = {}
            for mark in question_marks:
                topic = (mark.topic or "").strip()
                if not topic:
                    continue
                entry = per_topic.setdefault(topic, [0.0, 0.0])
                entry[0] += float(mark.marks_awarded or 0)
                entry[1] += float(mark.marks_available or 0)
            contributions = [
                (topic, awarded, available) for topic, (awarded, available) in per_topic.items()
            ]
        else:
            # Marked as a whole: the named weak topics are attempts we know went
            # badly, but with no marks to put behind them.
            contributions = [(topic, 0.0, 0.0) for topic in (marking.weak_topics or [])]

        for topic, awarded, available in contributions:
            key = (marking.subject, topic)
            row = totals.setdefault(key, [0, 0.0, 0.0, None])
            row[0] += 1
            row[1] += awarded
            row[2] += available
            if marking.marked_at and (row[3] is None or marking.marked_at > row[3]):
                row[3] = marking.marked_at

    existing = {
        (row.subject, row.topic): row
        for row in db.query(TopicMastery).filter(TopicMastery.child_id == child_id).all()
    }

    for key, (attempts, awarded, available, last_seen) in totals.items():
        subject, topic = key
        row = existing.pop(key, None)
        if not row:
            row = TopicMastery(
                id=str(uuid.uuid4()), child_id=child_id, subject=subject, topic=topic
            )
            db.add(row)

        row.attempts = attempts
        row.marks_awarded = awarded
        row.marks_available = available
        row.last_assessed_at = last_seen
        _grade(row)

    # Topics whose only evidence has gone leave no trace behind.
    for row in existing.values():
        db.delete(row)

    db.flush()


def _grade(row: TopicMastery) -> None:
    """Set the percentage and the weak/developing/secure band."""
    if row.marks_available and row.marks_available > 0:
        row.mastery_pct = round(row.marks_awarded / row.marks_available * 100, 1)
        if row.mastery_pct >= SECURE_TOPIC_THRESHOLD:
            row.status = "secure"
        elif row.mastery_pct >= WEAK_TOPIC_THRESHOLD:
            row.status = "developing"
        else:
            row.status = "weak"
    else:
        row.mastery_pct = None
        row.status = "weak"


# ---------------------------------------------------------------------------
# Putting a mark right
# ---------------------------------------------------------------------------


def set_mark(
    db: Session,
    marking: Marking,
    *,
    marks_awarded: Optional[float] = None,
    marks_available: Optional[float] = None,
) -> None:
    """
    Overwrite a total with one a person worked out.

    A hand-entered total settles the question, so the marking stops being
    something waiting for review and starts counting.
    """
    if marks_awarded is not None:
        marking.marks_awarded = marks_awarded
    if marks_available is not None:
        marking.marks_available = marks_available

    available = marking.marks_available or 0
    marking.percentage = (
        round((marking.marks_awarded or 0) / available * 100, 1) if available else None
    )
    marking.marked_by = "parent"
    marking.status = MARKED
    marking.review_reason = None

    _sync_score_log(db, marking)
    db.flush()


def _sync_score_log(db: Session, marking: Marking) -> None:
    """Keep the chart showing what the marking now says."""
    entry = (
        db.query(ScoreLogEntry).filter(ScoreLogEntry.marking_id == marking.id).first()
    )

    if marking.percentage is None:
        if entry:
            entry.deleted_at = datetime.utcnow()
        return

    if entry:
        entry.score_pct = marking.percentage
        entry.subject = marking.subject
        entry.deleted_at = None
        return

    # A paper that failed to mark never got a log entry; giving it a score now
    # should put it on the chart.
    db.add(
        ScoreLogEntry(
            id=str(uuid.uuid4()),
            child_id=marking.child_id,
            subject=marking.subject,
            label=_label_for(db, marking),
            score_pct=marking.percentage,
            source="marking",
            marking_id=marking.id,
            recorded_at=marking.marked_at or datetime.utcnow(),
        )
    )


def _label_for(db: Session, marking: Marking) -> str:
    """What to call this result on the chart."""
    assignment = (
        db.query(Assignment)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .filter(Submission.id == marking.submission_id)
        .first()
    )
    return (assignment.title if assignment else None) or marking.subject


# ---------------------------------------------------------------------------
# Knowing when not to believe a mark
# ---------------------------------------------------------------------------

# A child who hands in a paper has attempted most of it. Past this share of
# questions coming back as unanswered, the likelier story is that the scan was
# not read properly.
UNANSWERED_SHARE_THAT_LOOKS_WRONG = 0.6


def unbelievable(result) -> Optional[str]:
    """
    Why a marking result should not be trusted, or None if it looks sound.

    The failure that matters is not the marker erroring — that is visible — but
    the marker confidently returning nothing. A scan it could not read looks
    exactly like a paper the child left blank, and recording the second when it
    was the first puts a zero in the average that nobody meant.
    """
    if not result.marks_available:
        return "The marker could not work out what this paper was out of."

    verdicts = [m.verdict for m in result.question_marks]
    if verdicts:
        unanswered = sum(1 for v in verdicts if v == "not_attempted")
        if unanswered == len(verdicts):
            return "No answers could be found for any question on this paper."
        if unanswered / len(verdicts) >= UNANSWERED_SHARE_THAT_LOOKS_WRONG:
            return (
                f"{unanswered} of {len(verdicts)} questions came back with no answer "
                "found, which usually means the handwriting could not be read."
            )
    elif not result.percentage:
        return "The marker found no answers to mark."

    return None


def record_unmarked(
    db: Session,
    *,
    submission: Submission,
    subject: str,
    paper_id: Optional[str],
    reason: str,
    result=None,
) -> Marking:
    """
    Record work whose mark could not be trusted, without giving it a score.

    The work still counts as done — the child did it — but it carries no
    percentage, so it stays out of the average until a person supplies one.
    Whatever the marker did manage is kept, since a partial read is a useful
    starting point for marking by hand.
    """
    marking = Marking(
        id=str(uuid.uuid4()),
        submission_id=submission.id,
        child_id=submission.child_id,
        paper_id=paper_id,
        subject=subject,
        marks_awarded=None,
        marks_available=result.marks_available if result else None,
        percentage=None,
        overall_feedback=result.overall_feedback if result else None,
        strengths=result.strengths if result else [],
        weaknesses=result.weaknesses if result else [],
        weak_topics=[],  # Unverified marks must not decide what is weak.
        marked_by="ai",
        model=result.model if result else None,
        status=NEEDS_REVIEW,
        review_reason=reason,
        marked_at=datetime.utcnow(),
    )
    db.add(marking)
    db.flush()

    if result:
        from ..models_db import QuestionMark as QuestionMarkRow

        for mark in result.question_marks:
            db.add(
                QuestionMarkRow(
                    id=str(uuid.uuid4()),
                    marking_id=marking.id,
                    paper_question_id=mark.paper_question_id,
                    order_index=mark.order_index,
                    question_number=mark.question_number,
                    question_text=mark.question_text,
                    student_answer=mark.student_answer,
                    expected_answer=mark.expected_answer,
                    marks_awarded=mark.marks_awarded,
                    marks_available=mark.marks_available,
                    verdict=mark.verdict,
                    feedback=mark.feedback,
                    topic=mark.topic,
                )
            )

    db.flush()
    logger.info(f"Submission {submission.id} needs review: {reason}")
    return marking


def needs_review(
    db: Session,
    marking: Marking,
    *,
    reason: str,
) -> None:
    """
    Park a marking until someone can look at it.

    Its percentage is cleared rather than set to zero, which is what keeps it
    out of the average: a paper nobody could read is not a paper the child
    failed.
    """
    marking.status = NEEDS_REVIEW
    marking.review_reason = reason
    marking.percentage = None
    marking.marks_awarded = None

    _sync_score_log(db, marking)
    db.flush()
