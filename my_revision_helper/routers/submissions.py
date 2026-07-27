"""
Handing work in, and getting it marked.

A child uploads photos or a document of their completed paper. We store the
files, extract the text, then mark it against the paper's answer key and record
the result. Marking happens inline: it takes a few seconds and the child is
waiting for the feedback.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..file_processing import process_uploaded_files
from ..llm import get_openai_client, get_reasoning_model
from ..models_db import Assignment, Child, Marking, QuestionMark, Submission
from ..schemas.study import (
    MarkingListItem,
    MarkingListResponse,
    MarkingResponse,
    QuestionMarkOverrideRequest,
    QuestionMarkResponse,
)
from ..services import timing
from ..services.file_store import FileTooLargeError, get_file, store_uploads
from ..services.page_images import load_page_images, store_page_images
from ..services.marking_service import (
    load_paper_questions,
    mark_holistically,
    mark_per_question,
    persist_marking,
)
from ..services.scope import build_scope, ensure_user_row, get_owned_child, restrict_to_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required to hand work in. Set DATABASE_URL.",
        )
    return db


def _marking_response(db: Session, marking: Marking) -> MarkingResponse:
    submission = db.query(Submission).filter(Submission.id == marking.submission_id).first()
    question_marks = (
        db.query(QuestionMark)
        .filter(QuestionMark.marking_id == marking.id)
        .order_by(QuestionMark.order_index)
        .all()
    )

    return MarkingResponse(
        id=marking.id,
        submissionId=marking.submission_id,
        childId=marking.child_id,
        assignmentId=submission.assignment_id if submission else None,
        paperId=marking.paper_id,
        subject=marking.subject,
        marksAwarded=marking.marks_awarded,
        marksAvailable=marking.marks_available,
        percentage=marking.percentage,
        overallFeedback=marking.overall_feedback,
        strengths=marking.strengths or [],
        weaknesses=marking.weaknesses or [],
        weakTopics=marking.weak_topics or [],
        markedBy=marking.marked_by or "ai",
        markedAt=marking.marked_at.isoformat() if marking.marked_at else None,
        minutesSpent=submission.minutes_spent if submission else None,
        timed=bool(submission.timed) if submission else False,
        pauseCount=int(submission.pause_count or 0) if submission else 0,
        pageImageIds=(submission.page_image_ids or []) if submission else [],
        questionMarks=[
            QuestionMarkResponse(
                id=qm.id,
                orderIndex=qm.order_index,
                questionNumber=qm.question_number,
                questionText=qm.question_text,
                studentAnswer=qm.student_answer,
                expectedAnswer=qm.expected_answer,
                marksAwarded=qm.marks_awarded or 0,
                marksAvailable=qm.marks_available or 1,
                verdict=qm.verdict,
                feedback=qm.feedback,
                topic=qm.topic,
            )
            for qm in question_marks
        ],
    )


@router.post(
    "/assignments/{assignment_id}/submit", response_model=MarkingResponse, status_code=201
)
async def submit_assignment(
    assignment_id: str,
    note: str = Form(""),
    minutesSpent: Optional[int] = Form(None),
    pastedText: str = Form(""),
    files: List[UploadFile] = File(default_factory=list),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> MarkingResponse:
    """
    Hand in completed work and get it marked.

    Accepts photos of handwritten work, a document, or typed answers. The
    original files are kept so the work can be looked at again alongside the
    marks.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    assignment = restrict_to_owner(
        db.query(Assignment).filter(Assignment.id == assignment_id), Assignment, scope
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if not files and not pastedText.strip():
        raise HTTPException(
            status_code=400, detail="Upload a photo of your work or type your answers"
        )

    openai_client = get_openai_client()
    if not openai_client:
        raise HTTPException(
            status_code=503,
            detail="Marking is unavailable because OPENAI_API_KEY is not configured.",
        )

    try:
        file_ids, file_contents = await store_uploads(
            db, files, user_id=scope.user_id, session_id=scope.session_id
        )
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))

    # Keep every page as a picture as well as as text. A graph the child drew
    # cannot be written down, and it is often what the marks are for.
    page_image_ids = store_page_images(
        db, file_contents, user_id=scope.user_id, session_id=scope.session_id
    )

    extracted = await process_uploaded_files(files, openai_client)

    text_parts: List[str] = []
    if pastedText.strip():
        text_parts.append(pastedText.strip())
    for filename, text in extracted.items():
        text_parts.append(f"--- {filename} ---\n{text}")

    student_work = "\n\n".join(text_parts).strip()
    if not student_work:
        raise HTTPException(
            status_code=400,
            detail="Could not read any work from the upload. Try a clearer photo, or type your answers.",
        )

    # Handing in ends the sitting, whether or not "finish" was pressed.
    if assignment.timer_state in (timing.RUNNING, timing.PAUSED):
        timing.stop(assignment)

    measured = timing.logged_minutes(assignment)

    submission = Submission(
        id=str(uuid.uuid4()),
        assignment_id=assignment.id,
        child_id=assignment.child_id,
        # A measured time beats a typed one; the field is only a fallback now.
        minutes_spent=measured if measured is not None else minutesSpent,
        timed=measured is not None,
        pause_count=int(assignment.timer_pause_count or 0),
        note=note or None,
        extracted_text=student_work,
        file_ids=file_ids,
        page_image_ids=page_image_ids,
        uploaded_files=[f.filename for f in files if f.filename],
        status="marking",
    )
    db.add(submission)

    assignment.status = "submitted"
    db.commit()
    db.refresh(submission)

    questions = load_paper_questions(db, assignment.paper_id)
    child = db.query(Child).filter(Child.id == assignment.child_id).first()
    model = get_reasoning_model()

    try:
        if questions:
            result = mark_per_question(
                questions,
                student_work,
                subject=assignment.subject,
                client=openai_client,
                model=model,
                # So a question answered by drawing is marked from the drawing.
                pages=load_page_images(db, page_image_ids),
            )
        else:
            result = mark_holistically(
                student_work,
                subject=assignment.subject,
                year_group=child.year_group if child else None,
                client=openai_client,
                model=model,
            )
    except Exception as e:
        submission.status = "failed"
        # Back to where they were, not to untouched: the work was in fact done,
        # and a timed sitting should not look as though it never happened.
        assignment.status = "in_progress" if assignment.timer_first_started_at else "todo"
        db.commit()
        logger.error(f"Marking failed for submission {submission.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Marking failed: {e}")

    marking = persist_marking(
        db,
        submission=submission,
        subject=assignment.subject,
        paper_id=assignment.paper_id,
        result=result,
    )

    assignment.status = "marked"
    from datetime import datetime

    assignment.completed_at = datetime.utcnow()
    db.commit()

    return _marking_response(db, marking)


@router.get("/markings", response_model=MarkingListResponse)
async def list_markings(
    childId: Optional[str] = None,
    subject: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> MarkingListResponse:
    """Marked work, newest first."""
    if db is None:
        return MarkingListResponse(items=[], total=0)

    scope = build_scope(user, session_id)

    # Scope through assignments, which carry the owner columns.
    query = (
        db.query(Marking, Assignment)
        .join(Submission, Marking.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
    )
    query = restrict_to_owner(query, Assignment, scope)

    if childId:
        if not get_owned_child(db, childId, scope):
            raise HTTPException(status_code=404, detail="Child not found")
        query = query.filter(Marking.child_id == childId)
    if subject:
        query = query.filter(Marking.subject == subject)

    total = query.count()
    rows = query.order_by(Marking.marked_at.desc()).offset(offset).limit(limit).all()

    return MarkingListResponse(
        items=[
            MarkingListItem(
                id=marking.id,
                assignmentId=assignment.id,
                assignmentTitle=assignment.title,
                subject=marking.subject,
                percentage=marking.percentage,
                marksAwarded=marking.marks_awarded,
                marksAvailable=marking.marks_available,
                weakTopics=marking.weak_topics or [],
                markedAt=marking.marked_at.isoformat() if marking.marked_at else None,
            )
            for marking, assignment in rows
        ],
        total=total,
    )


def _owned_marking(db: Session, marking_id: str, scope) -> Optional[Marking]:
    """Fetch a marking only if the caller owns the assignment behind it."""
    query = (
        db.query(Marking)
        .join(Submission, Marking.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Marking.id == marking_id)
    )
    return restrict_to_owner(query, Assignment, scope).first()


@router.get("/markings/{marking_id}", response_model=MarkingResponse)
async def get_marking(
    marking_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> MarkingResponse:
    """Full marking detail, including the per-question breakdown."""
    db = _require_db(db)
    marking = _owned_marking(db, marking_id, build_scope(user, session_id))
    if not marking:
        raise HTTPException(status_code=404, detail="Marking not found")
    return _marking_response(db, marking)


@router.patch("/markings/{marking_id}/questions/{question_mark_id}", response_model=MarkingResponse)
async def override_question_mark(
    marking_id: str,
    question_mark_id: str,
    payload: QuestionMarkOverrideRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> MarkingResponse:
    """
    Correct the mark on a single question.

    The AI gets things wrong, particularly on extended written answers and on
    poorly-lit photos. Overriding recalculates the paper total and re-derives
    which topics count as weak, so a corrected mark feeds through to what gets
    retested.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    marking = _owned_marking(db, marking_id, scope)
    if not marking:
        raise HTTPException(status_code=404, detail="Marking not found")

    question_mark = (
        db.query(QuestionMark)
        .filter(QuestionMark.id == question_mark_id, QuestionMark.marking_id == marking_id)
        .first()
    )
    if not question_mark:
        raise HTTPException(status_code=404, detail="Question mark not found")

    available = float(question_mark.marks_available or 1)
    if payload.marksAwarded < 0 or payload.marksAwarded > available:
        raise HTTPException(
            status_code=400, detail=f"Marks must be between 0 and {available}"
        )

    question_mark.marks_awarded = payload.marksAwarded
    if payload.feedback is not None:
        question_mark.feedback = payload.feedback
    if payload.verdict:
        question_mark.verdict = payload.verdict
    else:
        # Keep the verdict consistent with the new mark.
        if payload.marksAwarded >= available:
            question_mark.verdict = "correct"
        elif payload.marksAwarded > 0:
            question_mark.verdict = "partial"
        else:
            question_mark.verdict = "incorrect"

    db.flush()
    _recalculate_marking(db, marking)
    db.commit()
    db.refresh(marking)

    return _marking_response(db, marking)


def _recalculate_marking(db: Session, marking: Marking) -> None:
    """Recompute a marking's totals and weak topics from its question marks."""
    from ..services.marking_service import WEAK_TOPIC_THRESHOLD

    question_marks = db.query(QuestionMark).filter(QuestionMark.marking_id == marking.id).all()
    if not question_marks:
        return

    awarded = sum(float(qm.marks_awarded or 0) for qm in question_marks)
    available = sum(float(qm.marks_available or 0) for qm in question_marks)

    marking.marks_awarded = round(awarded, 1)
    marking.marks_available = round(available, 1)
    marking.percentage = round(awarded / available * 100, 1) if available else None
    marking.marked_by = "parent"

    totals: Dict[str, List[float]] = {}
    for qm in question_marks:
        topic = (qm.topic or "").strip()
        if not topic:
            continue
        entry = totals.setdefault(topic, [0.0, 0.0])
        entry[0] += float(qm.marks_awarded or 0)
        entry[1] += float(qm.marks_available or 0)

    weak = sorted(
        (
            (values[0] / values[1] * 100, topic)
            for topic, values in totals.items()
            if values[1] > 0 and values[0] / values[1] * 100 < WEAK_TOPIC_THRESHOLD
        )
    )
    marking.weak_topics = [topic for _, topic in weak]

    # Keep the score log in step with the corrected total.
    from ..models_db import ScoreLogEntry

    entry = db.query(ScoreLogEntry).filter(ScoreLogEntry.marking_id == marking.id).first()
    if entry:
        entry.score_pct = marking.percentage


@router.get("/submissions/{submission_id}/files/{file_id}")
async def download_submission_file(
    submission_id: str,
    file_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """Retrieve a file that was handed in, e.g. to view the original photo."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    submission = (
        db.query(Submission)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Submission.id == submission_id)
    )
    submission = restrict_to_owner(submission, Assignment, scope).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    allowed = set(submission.file_ids or []) | set(submission.page_image_ids or [])
    if file_id not in allowed:
        raise HTTPException(status_code=404, detail="File is not part of this submission")

    stored = get_file(db, file_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Stored file is missing")

    return Response(
        content=stored.content,
        media_type=stored.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{stored.filename}"'},
    )
