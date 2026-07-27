"""
Assignments: the work each child has been given.

Two kinds exist, and the difference is how completion is established:

- `paper`: a paper from the library. The child hands work in, it gets marked,
  and the marks drive topic mastery.
- `task`: an instruction such as "read this book for two hours". There is
  nothing to mark, so the child confirms it and optionally logs the time.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..clock import local_today
from ..database import get_db
from ..deps import get_session_id
from ..models_db import (
    Assignment,
    Child,
    Marking,
    Paper,
    PaperQuestion,
    Submission,
)
from ..schemas.study import (
    AssignmentCreateRequest,
    AssignmentListResponse,
    AssignmentMarkingSummary,
    AssignmentResponse,
    AssignmentTimer,
    AssignmentUpdateRequest,
    SelfReportRequest,
)
from ..services import timing
from ..services.scope import build_scope, ensure_user_row, get_owned_child, restrict_to_owner
from ..services.worksheet import merge_resources, render_worksheet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

VALID_STATUSES = {"todo", "in_progress", "submitted", "marked", "done"}
VALID_TYPES = {"paper", "task"}
VALID_VERIFICATIONS = {"upload", "self_report", "timer", "none"}

# Statuses that mean the child has nothing further to do.
FINISHED_STATUSES = {"marked", "done"}


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required for assignments. Set DATABASE_URL.",
        )
    return db


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Accept an ISO date or datetime, tolerating a trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}")


def planned_on(assignment: Assignment):
    """
    The calendar date this work is meant to be done on, or None.

    Falls back to the due date so work assigned before scheduling existed still
    appears in a day view. Answers "what am I doing today".
    """
    chosen = assignment.scheduled_date or assignment.due_date
    return chosen.date() if chosen else None


def due_on(assignment: Assignment):
    """
    The calendar date this work has to be finished by, or None.

    The other way round from `planned_on`: a plan may schedule work early with no
    separate deadline, in which case the planned day is the deadline. Answers "is
    this late".
    """
    chosen = assignment.due_date or assignment.scheduled_date
    return chosen.date() if chosen else None


def serialise_assignment(
    db: Session,
    assignment: Assignment,
    *,
    question_count: Optional[int] = None,
    marking: Optional[Marking] = None,
    paper: Optional[Paper] = None,
) -> AssignmentResponse:
    """
    Build the API representation of an assignment.

    Shared with the progress endpoints. Pass question_count, marking and paper
    when they have already been fetched in bulk, to avoid a query per row.
    """
    if paper is None and assignment.paper_id:
        # Falls back to the relationship, which is a primary-key load and is
        # already cached in the session when the paper was fetched alongside.
        paper = assignment.paper
    if question_count is None:
        question_count = (
            db.query(PaperQuestion).filter(PaperQuestion.paper_id == assignment.paper_id).count()
            if assignment.paper_id
            else 0
        )

    if marking is None:
        marking = (
            db.query(Marking)
            .join(Submission, Marking.submission_id == Submission.id)
            .filter(Submission.assignment_id == assignment.id)
            .order_by(Marking.marked_at.desc())
            .first()
        )

    summary = None
    if marking:
        summary = AssignmentMarkingSummary(
            id=marking.id,
            percentage=marking.percentage,
            marksAwarded=marking.marks_awarded,
            marksAvailable=marking.marks_available,
            weakTopics=marking.weak_topics or [],
            markedAt=marking.marked_at.isoformat() if marking.marked_at else None,
        )

    return AssignmentResponse(
        id=assignment.id,
        childId=assignment.child_id,
        title=assignment.title,
        subject=assignment.subject,
        assignmentType=assignment.assignment_type or "paper",
        paperId=assignment.paper_id,
        instructions=assignment.instructions,
        resourceUrl=assignment.resource_url,
        resources=merge_resources(
            paper.resources if paper else None,
            assignment.resources,
            assignment.resource_url,
        ),
        estimatedMinutes=assignment.estimated_minutes,
        dueDate=assignment.due_date.isoformat() if assignment.due_date else None,
        scheduledDate=(
            assignment.scheduled_date.isoformat() if assignment.scheduled_date else None
        ),
        plannedOn=planned_on(assignment).isoformat() if planned_on(assignment) else None,
        dueOn=due_on(assignment).isoformat() if due_on(assignment) else None,
        isOverdue=(
            assignment.status not in FINISHED_STATUSES
            and due_on(assignment) is not None
            and due_on(assignment) < local_today()
        ),
        weekLabel=assignment.week_label,
        verification=assignment.verification or "upload",
        status=assignment.status or "todo",
        sortOrder=assignment.sort_order or 0,
        createdAt=assignment.created_at.isoformat() if assignment.created_at else "",
        completedAt=assignment.completed_at.isoformat() if assignment.completed_at else None,
        questionCount=question_count,
        latestMarking=summary,
        timer=AssignmentTimer(**asdict(timing.view(assignment))),
    )


def _create_one(
    db: Session,
    payload: AssignmentCreateRequest,
    child_id: str,
    scope,
) -> Assignment:
    """Validate and build a single assignment row."""
    if payload.assignmentType not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"assignmentType must be one of: {', '.join(sorted(VALID_TYPES))}",
        )
    if payload.verification not in VALID_VERIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"verification must be one of: {', '.join(sorted(VALID_VERIFICATIONS))}",
        )

    paper: Optional[Paper] = None
    if payload.assignmentType == "paper":
        if not payload.paperId:
            raise HTTPException(status_code=400, detail="A paper assignment needs a paperId")
        paper = restrict_to_owner(
            db.query(Paper).filter(Paper.id == payload.paperId), Paper, scope
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

    title = payload.title.strip() or (paper.title if paper else "")
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    return Assignment(
        id=str(uuid.uuid4()),
        child_id=child_id,
        user_id=scope.user_id,
        session_id=scope.session_id,
        title=title,
        assignment_type=payload.assignmentType,
        subject=payload.subject or (paper.subject if paper else ""),
        paper_id=payload.paperId if payload.assignmentType == "paper" else None,
        instructions=payload.instructions,
        resource_url=payload.resourceUrl,
        resources=merge_resources(
            None, [link.model_dump() for link in payload.resources or []]
        ),
        estimated_minutes=payload.estimatedMinutes
        or (paper.estimated_minutes if paper else None),
        due_date=_parse_date(payload.dueDate),
        scheduled_date=_parse_date(payload.scheduledDate),
        week_label=payload.weekLabel,
        verification=payload.verification,
        status="todo",
        sort_order=payload.sortOrder,
    )


@router.post("/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    payload: AssignmentCreateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentResponse:
    """Give a child a piece of work."""
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    if not get_owned_child(db, payload.childId, scope):
        raise HTTPException(status_code=404, detail="Child not found")

    assignment = _create_one(db, payload, payload.childId, scope)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    logger.info(f"Created assignment {assignment.id} for child {assignment.child_id}")
    return serialise_assignment(db, assignment)


@router.post("/assignments/bulk", response_model=AssignmentListResponse, status_code=201)
async def create_assignments_bulk(
    payload: Dict,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentListResponse:
    """
    Create several assignments at once, optionally across several children.

    Accepts `{childIds: [...], assignments: [...]}` where each assignment's own
    childId is optional and defaults to each id in childIds. This is how a
    week's worth of work gets handed out to both kids in one action.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    raw_assignments = payload.get("assignments") or []
    if not raw_assignments:
        raise HTTPException(status_code=400, detail="No assignments supplied")

    child_ids = payload.get("childIds") or []
    if not child_ids:
        child_ids = list({a.get("childId") for a in raw_assignments if a.get("childId")})
    if not child_ids:
        raise HTTPException(status_code=400, detail="No children supplied")

    for child_id in child_ids:
        if not get_owned_child(db, child_id, scope):
            raise HTTPException(status_code=404, detail=f"Child not found: {child_id}")

    created: List[Assignment] = []
    for child_id in child_ids:
        for index, raw in enumerate(raw_assignments):
            item = dict(raw)
            item["childId"] = child_id
            item.setdefault("sortOrder", index)
            request = AssignmentCreateRequest(**item)
            assignment = _create_one(db, request, child_id, scope)
            db.add(assignment)
            created.append(assignment)

    db.commit()
    for assignment in created:
        db.refresh(assignment)

    logger.info(f"Created {len(created)} assignments across {len(child_ids)} child(ren)")
    return AssignmentListResponse(
        items=[serialise_assignment(db, a) for a in created], total=len(created)
    )


@router.get("/assignments", response_model=AssignmentListResponse)
async def list_assignments(
    childId: Optional[str] = None,
    status: Optional[str] = None,
    subject: Optional[str] = None,
    outstanding: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentListResponse:
    """
    List assignments, newest first.

    Set `outstanding=true` for the child's to-do list: everything not yet
    finished, ordered by due date so the next thing to do is first.
    """
    if db is None:
        return AssignmentListResponse(items=[], total=0)

    scope = build_scope(user, session_id)
    query = restrict_to_owner(db.query(Assignment), Assignment, scope)

    if childId:
        if not get_owned_child(db, childId, scope):
            raise HTTPException(status_code=404, detail="Child not found")
        query = query.filter(Assignment.child_id == childId)
    if subject:
        query = query.filter(Assignment.subject == subject)
    if status:
        query = query.filter(Assignment.status == status)
    if outstanding:
        query = query.filter(Assignment.status.notin_(list(FINISHED_STATUSES)))

    total = query.count()

    if outstanding:
        # Nulls last so undated work sits behind anything with a deadline.
        query = query.order_by(
            Assignment.due_date.is_(None),
            Assignment.due_date.asc(),
            Assignment.sort_order.asc(),
        )
    else:
        query = query.order_by(Assignment.created_at.desc(), Assignment.sort_order.asc())

    assignments = query.offset(offset).limit(limit).all()
    return AssignmentListResponse(
        items=[serialise_assignment(db, a) for a in assignments], total=total
    )


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentResponse:
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return serialise_assignment(db, assignment)


@router.get("/assignments/{assignment_id}/worksheet", response_class=HTMLResponse)
async def get_assignment_worksheet(
    assignment_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> HTMLResponse:
    """
    The printable worksheet for an assignment.

    Deliberately not the uploaded document: that still contains the answer key
    for any workbook it came with. This is built from the parsed questions and
    the answer-key-stripped text, so it is safe to hand to a student and safe to
    print. Prerequisite links are printed on it with a QR code, because a
    worksheet's purpose is to leave the screen.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    paper = (
        db.query(Paper).filter(Paper.id == assignment.paper_id).first()
        if assignment.paper_id
        else None
    )

    questions = []
    if paper:
        questions = (
            db.query(PaperQuestion)
            .filter(PaperQuestion.paper_id == paper.id)
            .order_by(PaperQuestion.order_index)
            .all()
        )

    child = db.query(Child).filter(Child.id == assignment.child_id).first()

    html_doc = render_worksheet(
        title=assignment.title or (paper.title if paper else "Worksheet"),
        subject=assignment.subject,
        student_name=child.name if child else None,
        due_text=(
            f"Due {assignment.due_date:%a %d %b}" if assignment.due_date else None
        ),
        total_marks=paper.total_marks if paper else None,
        resources=merge_resources(
            paper.resources if paper else None,
            assignment.resources,
            assignment.resource_url,
        ),
        questions=questions,
        # Only ever the stripped text; paper.full_text would carry the key.
        fallback_text=(paper.question_text if paper and not questions else None)
        or (assignment.instructions if not paper else None),
    )

    return HTMLResponse(content=html_doc)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: str,
    payload: AssignmentUpdateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentResponse:
    """Edit an assignment, including moving it between statuses."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
            )
        assignment.status = payload.status
        assignment.completed_at = (
            datetime.utcnow() if payload.status in FINISHED_STATUSES else None
        )

    if payload.title is not None:
        assignment.title = payload.title.strip() or assignment.title
    if payload.instructions is not None:
        assignment.instructions = payload.instructions
    if payload.resourceUrl is not None:
        assignment.resource_url = payload.resourceUrl
    if payload.resources is not None:
        assignment.resources = merge_resources(
            None, [link.model_dump() for link in payload.resources]
        )
    if payload.estimatedMinutes is not None:
        assignment.estimated_minutes = payload.estimatedMinutes
    if payload.dueDate is not None:
        assignment.due_date = _parse_date(payload.dueDate)
    if payload.scheduledDate is not None:
        # An empty string clears the scheduling, which is how work gets dragged
        # back off a day.
        assignment.scheduled_date = _parse_date(payload.scheduledDate)
    if payload.weekLabel is not None:
        assignment.week_label = payload.weekLabel
    if payload.verification is not None:
        if payload.verification not in VALID_VERIFICATIONS:
            raise HTTPException(status_code=400, detail="Invalid verification type")
        assignment.verification = payload.verification
    if payload.sortOrder is not None:
        assignment.sort_order = payload.sortOrder

    db.commit()
    db.refresh(assignment)
    return serialise_assignment(db, assignment)


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """Withdraw an assignment, along with any work handed in against it."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    return {"deleted": True, "assignmentId": assignment_id}


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentResponse)
async def self_report_assignment(
    assignment_id: str,
    payload: SelfReportRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentResponse:
    """
    Mark a non-markable task as done.

    Used for instructions like "read for two hours": there is no work to grade,
    so we record the child's confirmation and the time they logged. Paper
    assignments are rejected here — those complete by being handed in and
    marked, and letting them be ticked off directly would produce assignments
    that look finished but have no score behind them.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if assignment.assignment_type == "paper":
        raise HTTPException(
            status_code=400,
            detail="Hand this paper in to complete it — upload your work for marking.",
        )

    # Finishing the work finishes the clock, so a child who forgets to press
    # "finish" does not leave it running all evening.
    if assignment.timer_state in (timing.RUNNING, timing.PAUSED):
        timing.stop(assignment)

    measured = timing.logged_minutes(assignment)

    submission = Submission(
        id=str(uuid.uuid4()),
        assignment_id=assignment.id,
        child_id=assignment.child_id,
        # A measured time beats a typed one; the field is only a fallback now.
        minutes_spent=measured if measured is not None else payload.minutesSpent,
        timed=measured is not None,
        pause_count=int(assignment.timer_pause_count or 0),
        note=payload.note,
        status="submitted",
    )
    db.add(submission)

    assignment.status = "done"
    assignment.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(assignment)

    logger.info(
        f"Assignment {assignment.id} self-reported complete "
        f"({submission.minutes_spent or 0} minutes, "
        f"{'timed' if measured is not None else 'self-reported'})"
    )
    return serialise_assignment(db, assignment)


@router.post("/assignments/{assignment_id}/timer/{action}", response_model=AssignmentResponse)
async def control_timer(
    assignment_id: str,
    action: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentResponse:
    """
    Start, pause, resume, finish or reset the clock on a sitting.

    The whole assignment comes back rather than just the timer, because starting
    the clock also moves the work to "in progress" and the caller should not have
    to guess that.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    try:
        if action == "reset":
            timing.reset(assignment)
        elif action in timing.ACTIONS:
            timing.ACTIONS[action](assignment)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"action must be one of: reset, {', '.join(sorted(timing.ACTIONS))}",
            )
    except timing.TimerError as e:
        # The child pressed something that no longer applies, usually because
        # another tab moved the timer on.
        raise HTTPException(status_code=409, detail=str(e))

    db.commit()
    db.refresh(assignment)

    return serialise_assignment(db, assignment)


@router.get("/children/{child_id}/todo", response_model=AssignmentListResponse)
async def child_todo_list(
    child_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> AssignmentListResponse:
    """
    What this child should do next.

    Overdue work first, then today's, then the rest of the week, then undated
    work. This is what the child's landing page reads.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    if not get_owned_child(db, child_id, scope):
        raise HTTPException(status_code=404, detail="Child not found")

    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.child_id == child_id,
            Assignment.status.notin_(list(FINISHED_STATUSES)),
        )
        .order_by(
            Assignment.due_date.is_(None),
            Assignment.due_date.asc(),
            Assignment.sort_order.asc(),
        )
        .limit(limit)
        .all()
    )

    return AssignmentListResponse(
        items=[serialise_assignment(db, a) for a in assignments],
        total=len(assignments),
    )


