"""
Progress: what each child has done, how they are tracking, and what to do next.

The dashboard and the child's landing page both read from a single endpoint so
they cannot disagree with each other, and so opening the app is one request
rather than a dozen.

Also hosts the retest endpoint, which turns the weak topics identified by
marking into a practice revision.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..models_db import (
    Assignment,
    Child,
    ChildSubject,
    Marking,
    PlanBlock,
    Revision,
    ScoreLogEntry,
    StudyPlan,
    Submission,
    TopicMastery,
)
from ..routers.assignments import FINISHED_STATUSES, serialise_assignment, week_bounds
from ..routers.children import _child_response, _plan_response
from ..schemas.study import (
    ChildProgressResponse,
    MarkingListItem,
    RetestRequest,
    RetestResponse,
    ScoreLogItem,
    SubjectProgressResponse,
    TopicMasteryResponse,
)
from ..services.marking_service import WEAK_TOPIC_THRESHOLD
from ..services.scope import build_scope, ensure_user_row, get_owned_child

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# How many topics a retest will cover at once. Beyond this the test stops being
# a focused retest and becomes a general paper.
MAX_RETEST_TOPICS = 6


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required for progress tracking. Set DATABASE_URL.",
        )
    return db


def _score_log_item(entry: ScoreLogEntry) -> ScoreLogItem:
    gap = None
    if entry.score_pct is not None and entry.year_average_pct is not None:
        gap = round(entry.score_pct - entry.year_average_pct, 1)

    return ScoreLogItem(
        id=entry.id,
        subject=entry.subject,
        label=entry.label,
        scorePct=entry.score_pct,
        yearAveragePct=entry.year_average_pct,
        gap=gap,
        source=entry.source or "manual",
        recordedAt=entry.recorded_at.isoformat() if entry.recorded_at else "",
    )


def _streak_days(db: Session, child_id: str) -> int:
    """
    Consecutive days up to today on which the child did something.

    Counts any submission, whether marked work or a self-reported task. Breaks
    on the first day with nothing. Yesterday counts as the start so that a
    streak is not lost simply because today's work has not happened yet.
    """
    submissions = (
        db.query(Submission.submitted_at)
        .filter(Submission.child_id == child_id)
        .order_by(Submission.submitted_at.desc())
        .all()
    )
    if not submissions:
        return 0

    active_days = {s.submitted_at.date() for s in submissions if s.submitted_at}
    if not active_days:
        return 0

    today = datetime.utcnow().date()
    cursor = today if today in active_days else today - timedelta(days=1)

    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.get("/children/{child_id}/progress", response_model=ChildProgressResponse)
async def get_child_progress(
    child_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ChildProgressResponse:
    """Everything the dashboard and landing page need, in one request."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    child = get_owned_child(db, child_id, scope)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    plan = (
        db.query(StudyPlan)
        .filter(StudyPlan.child_id == child_id, StudyPlan.is_active.is_(True))
        .order_by(StudyPlan.created_at.desc())
        .first()
    )
    plan_response = None
    if plan:
        blocks = db.query(PlanBlock).filter(PlanBlock.plan_id == plan.id).all()
        plan_response = _plan_response(plan, blocks)

    assignments = db.query(Assignment).filter(Assignment.child_id == child_id).all()
    markings = (
        db.query(Marking)
        .filter(Marking.child_id == child_id)
        .order_by(Marking.marked_at.desc())
        .all()
    )
    mastery = (
        db.query(TopicMastery)
        .filter(TopicMastery.child_id == child_id)
        .order_by(TopicMastery.mastery_pct.is_(None), TopicMastery.mastery_pct.asc())
        .all()
    )
    score_entries = (
        db.query(ScoreLogEntry)
        .filter(ScoreLogEntry.child_id == child_id)
        .order_by(ScoreLogEntry.recorded_at.asc())
        .all()
    )
    subject_rows = (
        db.query(ChildSubject)
        .filter(ChildSubject.child_id == child_id, ChildSubject.is_active.is_(True))
        .all()
    )

    week_start, week_end = week_bounds()

    minutes_this_week = 0
    for submission in (
        db.query(Submission)
        .filter(
            Submission.child_id == child_id,
            Submission.submitted_at >= week_start,
            Submission.submitted_at < week_end,
        )
        .all()
    ):
        minutes_this_week += submission.minutes_spent or 0

    # Per-subject rollup.
    latest_score_by_subject: Dict[str, float] = {}
    for entry in score_entries:
        if entry.score_pct is not None:
            latest_score_by_subject[entry.subject] = entry.score_pct

    minutes_by_subject: Dict[str, int] = {}
    for submission, assignment in (
        db.query(Submission, Assignment)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Submission.child_id == child_id)
        .all()
    ):
        if submission.minutes_spent:
            minutes_by_subject[assignment.subject] = (
                minutes_by_subject.get(assignment.subject, 0) + submission.minutes_spent
            )

    weak_by_subject: Dict[str, List[str]] = {}
    for row in mastery:
        if row.status == "weak":
            weak_by_subject.setdefault(row.subject, []).append(row.topic)

    subject_progress: List[SubjectProgressResponse] = []
    for row in subject_rows:
        subject_assignments = [a for a in assignments if a.subject == row.subject]
        done = [a for a in subject_assignments if a.status in FINISHED_STATUSES]
        latest = latest_score_by_subject.get(row.subject)

        subject_progress.append(
            SubjectProgressResponse(
                subject=row.subject,
                baselineScore=row.baseline_score,
                yearAverage=row.year_average,
                targetScore=row.target_score,
                latestScore=latest,
                gapToAverage=(
                    round(latest - row.year_average, 1)
                    if latest is not None and row.year_average is not None
                    else None
                ),
                baselineGap=(
                    round(row.baseline_score - row.year_average, 1)
                    if row.baseline_score is not None and row.year_average is not None
                    else None
                ),
                weeklyMinutes=row.weekly_minutes or 0,
                assignmentsTotal=len(subject_assignments),
                assignmentsDone=len(done),
                minutesLogged=minutes_by_subject.get(row.subject, 0),
                weakTopics=weak_by_subject.get(row.subject, [])[:5],
            )
        )

    # Worst gap first, matching how the plan prioritises time.
    subject_progress.sort(
        key=lambda s: (
            s.gapToAverage
            if s.gapToAverage is not None
            else (s.baselineGap if s.baselineGap is not None else 999)
        )
    )

    outstanding = [a for a in assignments if a.status not in FINISHED_STATUSES]
    outstanding.sort(key=lambda a: (a.due_date is None, a.due_date or datetime.max, a.sort_order or 0))

    completed = [a for a in assignments if a.status in FINISHED_STATUSES]
    due_this_week = [
        a for a in outstanding if a.due_date and week_start <= a.due_date < week_end
    ]

    # Overdue is compared on the date, not the instant. Work set for today is not
    # late during the evening it was set, which a timestamp comparison would say.
    today = datetime.now().date()
    overdue = [a for a in outstanding if a.due_date and a.due_date.date() < today]

    percentages = [m.percentage for m in markings if m.percentage is not None]

    return ChildProgressResponse(
        child=_child_response(child),
        plan=plan_response,
        subjects=subject_progress,
        scoreLog=[_score_log_item(e) for e in score_entries],
        weakTopics=[
            TopicMasteryResponse(
                subject=row.subject,
                topic=row.topic,
                attempts=row.attempts or 0,
                masteryPct=row.mastery_pct,
                status=row.status or "weak",
                lastAssessedAt=(
                    row.last_assessed_at.isoformat() if row.last_assessed_at else None
                ),
            )
            for row in mastery
            if row.status == "weak"
        ][:20],
        upNext=[serialise_assignment(db, a) for a in outstanding[:5]],
        recentMarkings=[
            MarkingListItem(
                id=m.id,
                subject=m.subject,
                percentage=m.percentage,
                marksAwarded=m.marks_awarded,
                marksAvailable=m.marks_available,
                weakTopics=m.weak_topics or [],
                markedAt=m.marked_at.isoformat() if m.marked_at else None,
            )
            for m in markings[:5]
        ],
        assignmentsTotal=len(assignments),
        assignmentsDone=len(completed),
        assignmentsDueThisWeek=len(due_this_week),
        assignmentsOverdue=len(overdue),
        minutesLoggedThisWeek=minutes_this_week,
        weeklyMinutesTarget=(plan.weekly_minutes_target or 0) if plan else 0,
        averagePercentage=(
            round(sum(percentages) / len(percentages), 1) if percentages else None
        ),
        streakDays=_streak_days(db, child_id),
    )


@router.get("/children/{child_id}/mastery", response_model=List[TopicMasteryResponse])
async def get_child_mastery(
    child_id: str,
    subject: Optional[str] = None,
    status: Optional[str] = None,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[TopicMasteryResponse]:
    """Per-topic performance, weakest first."""
    db = _require_db(db)
    if not get_owned_child(db, child_id, build_scope(user, session_id)):
        raise HTTPException(status_code=404, detail="Child not found")

    query = db.query(TopicMastery).filter(TopicMastery.child_id == child_id)
    if subject:
        query = query.filter(TopicMastery.subject == subject)
    if status:
        query = query.filter(TopicMastery.status == status)

    rows = query.order_by(
        TopicMastery.mastery_pct.is_(None), TopicMastery.mastery_pct.asc()
    ).all()

    return [
        TopicMasteryResponse(
            subject=row.subject,
            topic=row.topic,
            attempts=row.attempts or 0,
            masteryPct=row.mastery_pct,
            status=row.status or "weak",
            lastAssessedAt=row.last_assessed_at.isoformat() if row.last_assessed_at else None,
        )
        for row in rows
    ]


@router.get("/children/{child_id}/score-log", response_model=List[ScoreLogItem])
async def get_score_log(
    child_id: str,
    subject: Optional[str] = None,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[ScoreLogItem]:
    """Every recorded score against the year-group average, oldest first."""
    db = _require_db(db)
    if not get_owned_child(db, child_id, build_scope(user, session_id)):
        raise HTTPException(status_code=404, detail="Child not found")

    query = db.query(ScoreLogEntry).filter(ScoreLogEntry.child_id == child_id)
    if subject:
        query = query.filter(ScoreLogEntry.subject == subject)

    return [_score_log_item(e) for e in query.order_by(ScoreLogEntry.recorded_at.asc()).all()]


@router.post("/children/{child_id}/score-log", response_model=ScoreLogItem, status_code=201)
async def add_score_log_entry(
    child_id: str,
    payload: Dict,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ScoreLogItem:
    """
    Record a score by hand, for tests sat outside the app.

    Falls back to the subject's stored year average when none is supplied, so
    the gap can still be charted.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    if not get_owned_child(db, child_id, scope):
        raise HTTPException(status_code=404, detail="Child not found")

    subject = (payload.get("subject") or "").strip()
    label = (payload.get("label") or "").strip()
    if not subject or not label:
        raise HTTPException(status_code=400, detail="subject and label are required")

    def _number(key: str) -> Optional[float]:
        value = payload.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} must be a number")

    year_average = _number("yearAveragePct")
    if year_average is None:
        row = (
            db.query(ChildSubject)
            .filter(ChildSubject.child_id == child_id, ChildSubject.subject == subject)
            .first()
        )
        year_average = row.year_average if row else None

    entry = ScoreLogEntry(
        id=str(uuid.uuid4()),
        child_id=child_id,
        subject=subject,
        label=label,
        score_pct=_number("scorePct"),
        year_average_pct=year_average,
        source=payload.get("source") or "manual",
        notes=payload.get("notes"),
        recorded_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _score_log_item(entry)


@router.post("/children/{child_id}/retest", response_model=RetestResponse, status_code=201)
async def create_retest(
    child_id: str,
    payload: RetestRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> RetestResponse:
    """
    Build a practice test from what the child got wrong.

    Topics come from an explicit list, or from a specific marking's weak
    topics, or failing that from their weakest topics overall in the subject.

    This creates the revision definition only. The caller then starts a run
    against it with the existing POST /api/revisions/{id}/runs endpoint, which
    is what generates the questions — so retests use exactly the same question
    generation and marking as any other practice session.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    child = get_owned_child(db, child_id, scope)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    subject = (payload.subject or "").strip()
    topics = [t.strip() for t in payload.topics if t and t.strip()]
    source_marking_id: Optional[str] = None
    context_parts: List[str] = []

    if payload.markingId:
        marking = (
            db.query(Marking)
            .filter(Marking.id == payload.markingId, Marking.child_id == child_id)
            .first()
        )
        if not marking:
            raise HTTPException(status_code=404, detail="Marking not found")

        source_marking_id = marking.id
        subject = subject or marking.subject
        if not topics:
            topics = list(marking.weak_topics or [])

        # Give question generation the specific feedback, not just topic names,
        # so the retest targets the actual mistakes.
        from ..models_db import QuestionMark

        missed = (
            db.query(QuestionMark)
            .filter(
                QuestionMark.marking_id == marking.id,
                QuestionMark.verdict.in_(["incorrect", "partial", "not_attempted"]),
            )
            .order_by(QuestionMark.order_index)
            .all()
        )
        if missed:
            context_parts.append(
                "This student recently lost marks on the following, and this test should "
                "target the same skills with different questions:"
            )
            for qm in missed[:15]:
                detail = f"- {qm.topic or 'general'}: {qm.question_text[:160]}"
                if qm.feedback:
                    detail += f" (examiner note: {qm.feedback[:160]})"
                context_parts.append(detail)

    if not subject:
        raise HTTPException(status_code=400, detail="A subject is required")

    if not topics:
        weak = (
            db.query(TopicMastery)
            .filter(
                TopicMastery.child_id == child_id,
                TopicMastery.subject == subject,
                TopicMastery.status == "weak",
            )
            .order_by(TopicMastery.mastery_pct.is_(None), TopicMastery.mastery_pct.asc())
            .limit(MAX_RETEST_TOPICS)
            .all()
        )
        topics = [row.topic for row in weak]

    if not topics:
        # Nothing weak on record: fall back to the topics the school report
        # flagged, so the button still does something sensible on day one.
        subject_row = (
            db.query(ChildSubject)
            .filter(ChildSubject.child_id == child_id, ChildSubject.subject == subject)
            .first()
        )
        topics = list((subject_row.focus_topics if subject_row else None) or [])

    if not topics:
        raise HTTPException(
            status_code=400,
            detail=(
                "No weak topics on record for this subject yet. "
                "Hand in a marked paper first, or choose topics explicitly."
            ),
        )

    topics = topics[:MAX_RETEST_TOPICS]

    if context_parts:
        description = "\n".join(context_parts)
    else:
        description = (
            f"Retest for {child.name} on topics they have found difficult: "
            f"{', '.join(topics)}."
        )

    question_count = max(1, min(20, payload.questionCount))

    revision = Revision(
        id=str(uuid.uuid4()),
        user_id=scope.user_id,
        session_id=scope.session_id,
        child_id=child_id,
        source_marking_id=source_marking_id,
        name=f"Retest: {', '.join(topics[:3])}" + (" …" if len(topics) > 3 else ""),
        subject=subject,
        topics=topics,
        description=description,
        desired_question_count=question_count,
        accuracy_threshold=WEAK_TOPIC_THRESHOLD,
        question_style=payload.questionStyle or "free-text",
        extracted_texts={},
        uploaded_files=[],
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)

    logger.info(
        f"Created retest revision {revision.id} for child {child_id} "
        f"on {len(topics)} topic(s) in {subject}"
    )

    return RetestResponse(
        revisionId=revision.id,
        runId=None,
        subject=subject,
        topics=topics,
        questionCount=question_count,
    )


@router.get("/children/{child_id}/week", response_model=List[Dict])
async def get_week_view(
    child_id: str,
    weekCycle: Optional[str] = Query(None, pattern="^[AB]$"),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[Dict]:
    """
    The weekly timetable with this week's assignments slotted into it.

    Gives the child a day-by-day view: which two blocks today holds, and which
    assigned work belongs to each.
    """
    db = _require_db(db)
    if not get_owned_child(db, child_id, build_scope(user, session_id)):
        raise HTTPException(status_code=404, detail="Child not found")

    plan = (
        db.query(StudyPlan)
        .filter(StudyPlan.child_id == child_id, StudyPlan.is_active.is_(True))
        .order_by(StudyPlan.created_at.desc())
        .first()
    )
    if not plan:
        return []

    blocks = db.query(PlanBlock).filter(PlanBlock.plan_id == plan.id).all()
    if weekCycle:
        blocks = [b for b in blocks if b.week_cycle in (None, weekCycle)]

    week_start, week_end = week_bounds()
    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.child_id == child_id,
            Assignment.due_date >= week_start,
            Assignment.due_date < week_end,
        )
        .all()
    )

    days: List[Dict] = []
    for day_index in range(plan.days_per_week or 5):
        day_date = week_start + timedelta(days=day_index)
        day_blocks = sorted(
            (b for b in blocks if b.day_of_week == day_index), key=lambda b: b.block_index
        )

        day_assignments = [a for a in assignments if a.due_date and a.due_date.date() == day_date.date()]

        days.append(
            {
                "dayOfWeek": day_index,
                "date": day_date.date().isoformat(),
                "blocks": [
                    {
                        "blockIndex": b.block_index,
                        "subject": b.subject,
                        "focus": b.focus,
                        "plannedMinutes": b.planned_minutes or 50,
                        "weekCycle": b.week_cycle,
                        "assignments": [
                            serialise_assignment(db, a).model_dump()
                            for a in day_assignments
                            if a.subject == b.subject
                        ],
                    }
                    for b in day_blocks
                ],
                "unscheduled": [
                    serialise_assignment(db, a).model_dump()
                    for a in day_assignments
                    if not any(b.subject == a.subject for b in day_blocks)
                ],
            }
        )

    return days
