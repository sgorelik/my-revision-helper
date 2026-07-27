"""
Children: the profiles the whole app is organised around.

Children are not accounts. A parent signs in once and switches between kids, so
these endpoints are scoped to the parent's user (or anonymous session) and a
child id is only ever accepted after an ownership check.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..models_db import Child, ChildSubject, PlanBlock, StudyPlan
from ..schemas.study import (
    ChildCreateRequest,
    ChildListResponse,
    ChildResponse,
    ChildSubjectPayload,
    ChildSubjectResponse,
    ChildUpdateRequest,
    PlanBlockResponse,
    StudyPlanResponse,
)
from ..services.scope import build_scope, ensure_user_row, get_owned_child, restrict_to_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required to track children. Set DATABASE_URL.",
        )
    return db


def _child_response(child: Child) -> ChildResponse:
    return ChildResponse(
        id=child.id,
        name=child.name,
        yearGroup=child.year_group,
        school=child.school,
        colour=child.colour or "orange",
        avatarEmoji=child.avatar_emoji,
        isActive=bool(child.is_active),
        createdAt=child.created_at.isoformat() if child.created_at else "",
    )


def _plan_response(plan: StudyPlan, blocks: List[PlanBlock]) -> StudyPlanResponse:
    return StudyPlanResponse(
        id=plan.id,
        childId=plan.child_id,
        title=plan.title,
        summary=plan.summary,
        startDate=plan.start_date.isoformat() if plan.start_date else None,
        endDate=plan.end_date.isoformat() if plan.end_date else None,
        weeklyMinutesTarget=plan.weekly_minutes_target or 0,
        daysPerWeek=plan.days_per_week or 5,
        isActive=bool(plan.is_active),
        blocks=[
            PlanBlockResponse(
                id=b.id,
                dayOfWeek=b.day_of_week,
                blockIndex=b.block_index,
                subject=b.subject,
                focus=b.focus,
                plannedMinutes=b.planned_minutes or 50,
                weekCycle=b.week_cycle,
            )
            for b in sorted(blocks, key=lambda b: (b.day_of_week, b.block_index))
        ],
    )


@router.get("/children", response_model=ChildListResponse)
async def list_children(
    includeInactive: bool = False,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ChildListResponse:
    """List the children belonging to the caller."""
    if db is None:
        return ChildListResponse(items=[])

    scope = build_scope(user, session_id)
    query = restrict_to_owner(db.query(Child), Child, scope)
    if not includeInactive:
        query = query.filter(Child.is_active.is_(True))

    children = query.order_by(Child.sort_order, Child.created_at).all()
    return ChildListResponse(items=[_child_response(c) for c in children])


@router.post("/children", response_model=ChildResponse, status_code=201)
async def create_child(
    payload: ChildCreateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ChildResponse:
    """Add a child profile."""
    db = _require_db(db)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    existing_count = restrict_to_owner(db.query(Child), Child, scope).count()

    child = Child(
        id=str(uuid.uuid4()),
        user_id=scope.user_id,
        session_id=scope.session_id,
        name=name,
        year_group=payload.yearGroup,
        school=payload.school,
        colour=payload.colour or "orange",
        avatar_emoji=payload.avatarEmoji,
        sort_order=existing_count,
        is_active=True,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    logger.info(f"Created child {child.id} ({child.name})")
    return _child_response(child)


@router.get("/children/{child_id}", response_model=ChildResponse)
async def get_child(
    child_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ChildResponse:
    db = _require_db(db)
    child = get_owned_child(db, child_id, build_scope(user, session_id))
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return _child_response(child)


@router.patch("/children/{child_id}", response_model=ChildResponse)
async def update_child(
    child_id: str,
    payload: ChildUpdateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> ChildResponse:
    db = _require_db(db)
    child = get_owned_child(db, child_id, build_scope(user, session_id))
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        child.name = name
    if payload.yearGroup is not None:
        child.year_group = payload.yearGroup
    if payload.school is not None:
        child.school = payload.school
    if payload.colour is not None:
        child.colour = payload.colour
    if payload.avatarEmoji is not None:
        child.avatar_emoji = payload.avatarEmoji
    if payload.isActive is not None:
        child.is_active = payload.isActive

    db.commit()
    db.refresh(child)
    return _child_response(child)


@router.delete("/children/{child_id}")
async def delete_child(
    child_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Remove a child and everything belonging to them.

    Requires a signed-in parent: deletion is destructive and an anonymous
    session should not be able to wipe a family's history.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    if not scope.is_authenticated:
        raise HTTPException(status_code=401, detail="Sign in to delete a child")

    child = get_owned_child(db, child_id, scope)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    db.delete(child)
    db.commit()
    logger.info(f"Deleted child {child_id}")
    return {"deleted": True, "childId": child_id}


# ---------------------------------------------------------------------------
# Subject baselines
# ---------------------------------------------------------------------------


def _subject_response(row: ChildSubject) -> ChildSubjectResponse:
    gap = None
    if row.baseline_score is not None and row.year_average is not None:
        gap = round(row.baseline_score - row.year_average, 1)

    return ChildSubjectResponse(
        id=row.id,
        subject=row.subject,
        baselineScore=row.baseline_score,
        yearAverage=row.year_average,
        targetScore=row.target_score,
        weeklyMinutes=row.weekly_minutes or 0,
        priority=row.priority or 0,
        focusTopics=row.focus_topics or [],
        reportNotes=row.report_notes,
        gap=gap,
    )


@router.get("/children/{child_id}/subjects", response_model=List[ChildSubjectResponse])
async def list_child_subjects(
    child_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[ChildSubjectResponse]:
    """Subject baselines for a child, worst gap first."""
    db = _require_db(db)
    child = get_owned_child(db, child_id, build_scope(user, session_id))
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    rows = (
        db.query(ChildSubject)
        .filter(ChildSubject.child_id == child_id, ChildSubject.is_active.is_(True))
        .all()
    )

    responses = [_subject_response(r) for r in rows]
    # Biggest shortfall against the year average first; that is the order the
    # plan itself uses to justify time allocation.
    responses.sort(key=lambda r: (r.gap if r.gap is not None else 999, -r.priority))
    return responses


@router.put("/children/{child_id}/subjects", response_model=List[ChildSubjectResponse])
async def replace_child_subjects(
    child_id: str,
    payload: List[ChildSubjectPayload],
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[ChildSubjectResponse]:
    """
    Replace the full subject list for a child.

    Upserts by subject name so that re-importing a report keeps the existing
    rows (and therefore anything referencing them) rather than churning ids.
    """
    db = _require_db(db)
    child = get_owned_child(db, child_id, build_scope(user, session_id))
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    existing = {
        row.subject: row
        for row in db.query(ChildSubject).filter(ChildSubject.child_id == child_id).all()
    }
    submitted = set()

    for item in payload:
        subject = item.subject.strip()
        if not subject:
            continue
        submitted.add(subject)

        row = existing.get(subject)
        if not row:
            row = ChildSubject(id=str(uuid.uuid4()), child_id=child_id, subject=subject)
            db.add(row)

        row.baseline_score = item.baselineScore
        row.year_average = item.yearAverage
        row.target_score = item.targetScore
        row.weekly_minutes = item.weeklyMinutes
        row.priority = item.priority
        row.focus_topics = item.focusTopics
        row.report_notes = item.reportNotes
        row.is_active = True

    # Subjects left out of the payload are deactivated, not deleted, so their
    # score history survives.
    for subject, row in existing.items():
        if subject not in submitted:
            row.is_active = False

    db.commit()

    return await list_child_subjects(child_id, user, db, session_id)


# ---------------------------------------------------------------------------
# Study plan
# ---------------------------------------------------------------------------


@router.get("/children/{child_id}/plan", response_model=Optional[StudyPlanResponse])
async def get_child_plan(
    child_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> Optional[StudyPlanResponse]:
    """The child's active study plan and weekly timetable."""
    db = _require_db(db)
    child = get_owned_child(db, child_id, build_scope(user, session_id))
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    plan = (
        db.query(StudyPlan)
        .filter(StudyPlan.child_id == child_id, StudyPlan.is_active.is_(True))
        .order_by(StudyPlan.created_at.desc())
        .first()
    )
    if not plan:
        return None

    blocks = db.query(PlanBlock).filter(PlanBlock.plan_id == plan.id).all()
    return _plan_response(plan, blocks)


def create_plan_with_blocks(
    db: Session,
    *,
    child_id: str,
    title: str,
    summary: Optional[str] = None,
    source_text: Optional[str] = None,
    weekly_minutes_target: int = 0,
    days_per_week: int = 5,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    blocks: Optional[List[dict]] = None,
) -> StudyPlan:
    """
    Create a plan and its timetable, deactivating any previous plan.

    Shared with the import script, which is why it takes plain values rather
    than a request model.
    """
    db.query(StudyPlan).filter(
        StudyPlan.child_id == child_id, StudyPlan.is_active.is_(True)
    ).update({"is_active": False})

    plan = StudyPlan(
        id=str(uuid.uuid4()),
        child_id=child_id,
        title=title,
        summary=summary,
        source_text=source_text,
        weekly_minutes_target=weekly_minutes_target,
        days_per_week=days_per_week,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    db.add(plan)
    db.flush()

    for block in blocks or []:
        db.add(
            PlanBlock(
                id=str(uuid.uuid4()),
                plan_id=plan.id,
                day_of_week=block["dayOfWeek"],
                block_index=block["blockIndex"],
                subject=block["subject"],
                focus=block.get("focus"),
                planned_minutes=block.get("plannedMinutes", 50),
                week_cycle=block.get("weekCycle"),
            )
        )

    db.commit()
    db.refresh(plan)
    return plan
