"""
Correcting a child's record, one piece of work at a time.

Until now the only way to remove a wrong entry was to delete the child and
start again, and a mark the app got wrong could not be changed at all. Both are
ordinary things to need: an auto-marker that reads a scan badly will sometimes
score a good paper at 42%, and that number sits in the average until someone
can reach it.

"Work" here means the assignment together with its submission and marking. They
are one thing to a parent, so they move, hide and come back together.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..models_db import Assignment, Marking, ScoreLogEntry, Submission
from ..schemas.study import (
    WorkItem,
    WorkListResponse,
    WorkMoveRequest,
    WorkUpdateRequest,
)
from ..services import work as work_service
from ..services.scope import build_scope, ensure_user_row, get_owned_child, restrict_to_owner
from ..subjects import normalise_subject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="A database is required.")
    return db


def _find_work(db: Session, work_id: str, scope) -> Assignment:
    """
    The assignment behind a work id.

    Accepts a marking id too: the lists a parent is looking at are lists of
    marks, so that is the id they have to hand.
    """
    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == work_id), Assignment, scope
    ).first()
    if assignment:
        return assignment

    found = (
        restrict_to_owner(
            db.query(Assignment)
            .join(Submission, Submission.assignment_id == Assignment.id)
            .join(Marking, Marking.submission_id == Submission.id)
            .filter(Marking.id == work_id),
            Assignment,
            scope,
        )
        .first()
    )
    if found:
        return found

    raise HTTPException(status_code=404, detail="That piece of work was not found")


def _latest_marking(db: Session, assignment: Assignment) -> tuple:
    """The submission and marking for a piece of work, newest first."""
    submission = (
        db.query(Submission)
        .filter(Submission.assignment_id == assignment.id)
        .order_by(Submission.submitted_at.desc())
        .first()
    )
    if not submission:
        return None, None

    marking = (
        db.query(Marking)
        .filter(Marking.submission_id == submission.id)
        .order_by(Marking.marked_at.desc())
        .first()
    )
    return submission, marking


def _serialise(assignment: Assignment, submission, marking) -> WorkItem:
    when = assignment.completed_at or assignment.scheduled_date or assignment.due_date

    if marking is None:
        status = "unmarked"
    elif marking.status == work_service.NEEDS_REVIEW:
        status = work_service.NEEDS_REVIEW
    else:
        status = "marked"

    return WorkItem(
        id=assignment.id,
        markingId=marking.id if marking else None,
        submissionId=submission.id if submission else None,
        childId=assignment.child_id,
        title=assignment.title,
        subject=assignment.subject,
        doneOn=when.isoformat() if when else None,
        marksAwarded=marking.marks_awarded if marking else None,
        marksAvailable=marking.marks_available if marking else None,
        percentage=marking.percentage if marking else None,
        status=status,
        reviewReason=marking.review_reason if marking else None,
        markedBy=marking.marked_by if marking else None,
        minutesSpent=submission.minutes_spent if submission else None,
        note=submission.note if submission else None,
        weakTopics=(marking.weak_topics or []) if marking else [],
        deletedAt=assignment.deleted_at.isoformat() if assignment.deleted_at else None,
    )


@router.get("/work", response_model=WorkListResponse)
async def list_work(
    childId: str = Query(...),
    includeDeleted: bool = Query(False),
    needsReviewOnly: bool = Query(False),
    limit: int = Query(50, le=200),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> WorkListResponse:
    """
    A child's completed work, newest first, as things that can be corrected.

    Includes work that could not be marked, which is the point: it is waiting
    for someone to give it a score.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    child = get_owned_child(db, childId, scope)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    query = db.query(Assignment).filter(
        Assignment.child_id == childId,
        Assignment.status.in_(["marked", "done", "submitted"]),
    )
    if not includeDeleted:
        query = work_service.live(query, Assignment)

    assignments = query.order_by(Assignment.completed_at.desc().nullslast()).limit(limit).all()

    items = []
    for assignment in assignments:
        submission, marking = _latest_marking(db, assignment)
        item = _serialise(assignment, submission, marking)
        if needsReviewOnly and item.status == "marked":
            continue
        items.append(item)

    return WorkListResponse(items=items, total=len(items))


@router.patch("/work/{work_id}", response_model=WorkItem)
async def update_work(
    work_id: str,
    payload: WorkUpdateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> WorkItem:
    """
    Correct a piece of work: its mark, what it was called, or when it was done.

    A mark entered here is taken as the truth — it replaces whatever the app
    worked out, and lifts the work out of needing review.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    assignment = _find_work(db, work_id, scope)
    submission, marking = _latest_marking(db, assignment)

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="A title cannot be empty")
        assignment.title = title

    if payload.subject is not None:
        subject = normalise_subject(payload.subject)
        if not subject:
            raise HTTPException(status_code=400, detail="A subject is needed")
        assignment.subject = subject
        if marking:
            marking.subject = subject

    if payload.doneOn is not None:
        try:
            parsed = datetime.fromisoformat(payload.doneOn.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date: {payload.doneOn}")
        when = datetime.combine(parsed.date(), datetime.min.time())
        assignment.completed_at = when
        assignment.scheduled_date = when
        assignment.due_date = when
        if submission:
            submission.submitted_at = when

    if payload.note is not None and submission:
        submission.note = payload.note.strip() or None

    if payload.minutesSpent is not None:
        if payload.minutesSpent < 0:
            raise HTTPException(status_code=400, detail="Time spent cannot be negative.")
        if submission:
            submission.minutes_spent = payload.minutesSpent

    if payload.marksAwarded is not None or payload.marksAvailable is not None:
        if not marking:
            raise HTTPException(
                status_code=400,
                detail="There is no marking on this work to correct.",
            )

        awarded = (
            payload.marksAwarded if payload.marksAwarded is not None else marking.marks_awarded
        )
        available = (
            payload.marksAvailable
            if payload.marksAvailable is not None
            else marking.marks_available
        )

        if not available:
            raise HTTPException(
                status_code=400, detail="Give the total the work was out of, e.g. 18 out of 25."
            )
        if awarded is None or awarded < 0:
            raise HTTPException(status_code=400, detail="A score cannot be negative.")
        if awarded > available:
            raise HTTPException(
                status_code=400, detail="The score cannot be more than the total available."
            )

        work_service.set_mark(
            db, marking, marks_awarded=awarded, marks_available=available
        )
        assignment.status = "marked"

    db.flush()
    # A new title or date changes what the chart should show even though the
    # mark itself has not moved.
    if marking:
        work_service.refresh_score_log(db, marking)
    work_service.recompute_mastery(db, assignment.child_id)
    db.commit()

    submission, marking = _latest_marking(db, assignment)
    return _serialise(assignment, submission, marking)


@router.delete("/work/{work_id}", response_model=WorkItem)
async def delete_work(
    work_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> WorkItem:
    """
    Take a piece of work off the record.

    It stops counting towards anything immediately, but is kept: the scan
    behind it is often the only copy, and deletions get regretted.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = _find_work(db, work_id, scope)
    if assignment.deleted_at:
        raise HTTPException(status_code=409, detail="That work is already off the record")

    work_service.soft_delete(db, assignment)
    db.commit()

    submission, marking = _latest_marking(db, assignment)
    return _serialise(assignment, submission, marking)


@router.post("/work/{work_id}/restore", response_model=WorkItem)
async def restore_work(
    work_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> WorkItem:
    """Put back a piece of work that was taken off the record."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = _find_work(db, work_id, scope)
    if not assignment.deleted_at:
        raise HTTPException(status_code=409, detail="That work is already on the record")

    work_service.restore(db, assignment)
    db.commit()

    submission, marking = _latest_marking(db, assignment)
    return _serialise(assignment, submission, marking)


@router.post("/work/{work_id}/move", response_model=WorkItem)
async def move_work(
    work_id: str,
    payload: WorkMoveRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> WorkItem:
    """
    Move a piece of work to a different child.

    Both children's figures are rebuilt: the one who did not do it loses the
    mark, and the one who did gains it.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    assignment = _find_work(db, work_id, scope)
    destination = get_owned_child(db, payload.toChildId, scope)
    if not destination:
        raise HTTPException(status_code=404, detail="Child not found")

    origin_id = assignment.child_id
    if origin_id == destination.id:
        raise HTTPException(status_code=400, detail="That work is already theirs")

    submissions = db.query(Submission).filter(Submission.assignment_id == assignment.id).all()
    markings = (
        db.query(Marking)
        .filter(Marking.submission_id.in_([s.id for s in submissions] or [""]))
        .all()
    )

    assignment.child_id = destination.id
    for submission in submissions:
        submission.child_id = destination.id
    for marking in markings:
        marking.child_id = destination.id

    if markings:
        for entry in (
            db.query(ScoreLogEntry)
            .filter(ScoreLogEntry.marking_id.in_([m.id for m in markings]))
            .all()
        ):
            entry.child_id = destination.id

    db.flush()
    work_service.recompute_mastery(db, origin_id)
    work_service.recompute_mastery(db, destination.id)
    db.commit()

    submission, marking = _latest_marking(db, assignment)
    logger.info(f"Moved work {assignment.id} from {origin_id} to {destination.id}")
    return _serialise(assignment, submission, marking)
