"""
Handing in work that was never assigned.

Most work goes out through the app and comes back to be marked. Some does not: a
worksheet the child had on paper, an exercise set in class, a past paper worked
through at the kitchen table. This records that after the fact, in one request,
rather than making the parent build an assignment first and then hand in against
it.

Two shapes of hand-in:

With a scan, where the questions and the child's answers sit side by side on the
page. The transcription marks which words the child wrote, so taking those out
leaves the blank paper, which goes into the library ready for the other child and
gives the marker its questions.

Without a scan, for work done on paper that nobody wants to photograph. Nothing
can be marked, but the work still happened, and a score the parent already knows
can be recorded so it reaches the progress chart.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..clock import local_today
from ..database import get_db
from ..deps import get_session_id
from ..file_processing import process_uploaded_files
from ..llm import get_openai_client, get_reasoning_model
from ..models_db import Assignment, Child, Paper, PaperQuestion, Submission
from ..schemas.study import HandInResponse
from ..services.file_store import FileTooLargeError, store_uploads
from ..services.marking_service import (
    MarkingResult,
    load_paper_questions,
    mark_holistically,
    mark_per_question,
    persist_marking,
)
from ..services.page_images import load_page_images, store_page_images
from ..services.paper_parser import guess_title, parse_paper
from ..services.scope import build_scope, ensure_user_row, get_owned_child, owner_columns
from ..services.student_writing import (
    has_student_writing,
    looks_self_contained,
    strip_student_writing,
)
from ..subjects import normalise_subject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required to hand work in. Set DATABASE_URL.",
        )
    return db


def _day_done(value: str) -> datetime:
    """
    The day the work was done, as midnight local time.

    Defaults to today. Kept as a plain date rather than a moment because nobody
    records the hour they finished a worksheet, and the week it falls in is what
    the chart cares about.
    """
    if not value:
        return datetime.combine(local_today(), datetime.min.time())
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}")
    return datetime.combine(parsed.date(), datetime.min.time())


def _fallback_title(subject: str, done_on: datetime) -> str:
    """A name for work that neither the parent nor the paper named."""
    return f"{subject} work, {done_on.strftime('%-d %b')}"


def _record_assignment(
    db: Session,
    scope,
    *,
    child: Child,
    title: str,
    subject: str,
    paper: Optional[Paper],
    done_on: datetime,
    minutes: Optional[int],
    instructions: Optional[str],
) -> Assignment:
    """
    An assignment for work that has already been done.

    Created finished rather than to-do, and dated to the day the work happened
    so it lands in the right week on the chart instead of today's.
    """
    return Assignment(
        id=str(uuid.uuid4()),
        **owner_columns(scope),
        child_id=child.id,
        paper_id=paper.id if paper else None,
        title=title,
        subject=subject,
        assignment_type="paper" if paper else "task",
        instructions=instructions or None,
        estimated_minutes=minutes,
        scheduled_date=done_on,
        due_date=done_on,
        # Marking, where there is any, moves this on to "marked".
        status="done",
        verification="upload" if paper else "self_report",
        completed_at=done_on,
        created_at=datetime.utcnow(),
    )


async def _paper_from_completed_work(
    db: Session,
    scope,
    *,
    tagged_text: str,
    title: str,
    subject: str,
    file_ids: List[str],
) -> Optional[Paper]:
    """
    The blank paper behind a completed scan, saved for re-use.

    Returns None when the scan cannot give one up: a page of bare answers with no
    questions on it, or a transcription that never marked the handwriting, in
    which case stripping would leave the child's answers in the library copy.
    """
    if not has_student_writing(tagged_text) or not looks_self_contained(tagged_text):
        logger.info("Hand-in does not carry its own questions; marking it as a whole")
        return None

    printed = strip_student_writing(tagged_text)
    openai_client = get_openai_client()

    parsed = parse_paper(
        printed,
        subject=subject,
        client=openai_client,
        model=get_reasoning_model() if openai_client else None,
    )
    if not parsed.questions:
        logger.info("No questions found in the stripped scan; marking it as a whole")
        return None

    paper = Paper(
        id=str(uuid.uuid4()),
        **owner_columns(scope),
        title=title or parsed.title or guess_title(printed) or f"{subject} worksheet",
        subject=subject,
        paper_type="worksheet",
        topics=parsed.topics or [],
        source_file_id=file_ids[0] if file_ids else None,
        # The printed half only. Storing the transcription as it arrived would
        # put one child's answers in front of the next one to be given this.
        full_text=printed,
        question_text=parsed.question_text,
        answer_key_text=None,
        total_marks=parsed.total_marks,
        estimated_minutes=parsed.estimated_minutes,
        parse_status=parsed.parse_status,
        parse_error=parsed.parse_error,
        parsed_at=datetime.utcnow(),
    )
    db.add(paper)
    db.flush()

    for question in parsed.questions:
        db.add(
            PaperQuestion(
                id=str(uuid.uuid4()),
                paper_id=paper.id,
                session_label=question.session_label,
                band=question.band,
                number=question.number,
                order_index=question.order_index,
                question_text=question.question_text,
                marks=question.marks,
                topic=question.topic,
                # There was no answer key with it, so the marker works from
                # subject knowledge instead.
                expected_answer=None,
                marking_notes=question.marking_notes,
            )
        )

    db.flush()
    return paper


def _manual_result(
    *,
    marks_awarded: float,
    marks_available: float,
    note: Optional[str],
) -> MarkingResult:
    """A score the parent already worked out, in the shape marking expects."""
    percentage = round(marks_awarded / marks_available * 100, 1) if marks_available else None
    return MarkingResult(
        marks_awarded=marks_awarded,
        marks_available=marks_available,
        percentage=percentage,
        overall_feedback=note or "Marked on paper.",
        model=None,
    )


@router.post("/handins", response_model=HandInResponse, status_code=201)
async def hand_in_unassigned_work(
    childId: str = Form(...),
    subject: str = Form(...),
    title: str = Form(""),
    note: str = Form(""),
    doneOn: str = Form(""),
    minutesSpent: Optional[int] = Form(None),
    pastedText: str = Form(""),
    marksAwarded: Optional[float] = Form(None),
    marksAvailable: Optional[float] = Form(None),
    saveToLibrary: bool = Form(True),
    files: List[UploadFile] = File(default_factory=list),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> HandInResponse:
    """
    Record work that was never assigned, and mark it if there is something to mark.

    Send a scan (or typed answers) to have it marked question by question. Send
    no work at all to record that it was done, optionally with the score you
    already know.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    child = get_owned_child(db, childId, scope)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    subject = normalise_subject(subject)
    if not subject:
        raise HTTPException(status_code=400, detail="A subject is needed")

    if marksAwarded is not None and not marksAvailable:
        raise HTTPException(
            status_code=400,
            detail="Give the total the work was out of as well, e.g. 18 out of 25.",
        )
    if marksAwarded is not None and marksAvailable and marksAwarded > marksAvailable:
        raise HTTPException(
            status_code=400, detail="The score cannot be more than the total available."
        )

    done_on = _day_done(doneOn)
    has_work = bool(files) or bool(pastedText.strip())

    if not has_work and marksAwarded is None and minutesSpent is None:
        raise HTTPException(
            status_code=400,
            detail="Add the work, a score, or the time spent — otherwise there is nothing to record.",
        )

    if not has_work:
        return _record_without_work(
            db,
            scope,
            child=child,
            title=title.strip() or _fallback_title(subject, done_on),
            subject=subject,
            done_on=done_on,
            minutes=minutesSpent,
            note=note,
            marks_awarded=marksAwarded,
            marks_available=marksAvailable,
        )

    return await _record_with_work(
        db,
        scope,
        child=child,
        # Left as typed. A paper usually says what it is, and the parser reads
        # that off the page better than a date stamp does.
        title=title.strip(),
        subject=subject,
        done_on=done_on,
        minutes=minutesSpent,
        note=note,
        pasted_text=pastedText,
        files=files,
        save_to_library=saveToLibrary,
        marks_awarded=marksAwarded,
        marks_available=marksAvailable,
    )


def _record_without_work(
    db: Session,
    scope,
    *,
    child: Child,
    title: str,
    subject: str,
    done_on: datetime,
    minutes: Optional[int],
    note: str,
    marks_awarded: Optional[float],
    marks_available: Optional[float],
) -> HandInResponse:
    """Work done on paper and never scanned: record that it happened."""
    from .submissions import _marking_response

    assignment = _record_assignment(
        db,
        scope,
        child=child,
        title=title,
        subject=subject,
        paper=None,
        done_on=done_on,
        minutes=minutes,
        instructions=None,
    )
    db.add(assignment)
    db.flush()

    submission = Submission(
        id=str(uuid.uuid4()),
        assignment_id=assignment.id,
        child_id=child.id,
        minutes_spent=minutes,
        timed=False,
        pause_count=0,
        note=note or None,
        submitted_at=done_on,
        status="submitted",
    )
    db.add(submission)
    db.flush()

    if marks_awarded is None:
        db.commit()
        logger.info(f"Recorded unscanned work for {child.id}: {title}")
        return HandInResponse(
            assignmentId=assignment.id,
            submissionId=submission.id,
            childId=child.id,
            subject=subject,
            title=title,
        )

    marking = persist_marking(
        db,
        submission=submission,
        subject=subject,
        paper_id=None,
        result=_manual_result(
            marks_awarded=marks_awarded,
            marks_available=marks_available or 0,
            note=note,
        ),
        marked_by="parent",
    )
    assignment.status = "marked"
    db.commit()

    return HandInResponse(
        assignmentId=assignment.id,
        submissionId=submission.id,
        childId=child.id,
        subject=subject,
        title=title,
        marking=_marking_response(db, marking),
    )


async def _record_with_work(
    db: Session,
    scope,
    *,
    child: Child,
    title: str,
    subject: str,
    done_on: datetime,
    minutes: Optional[int],
    note: str,
    pasted_text: str,
    files: List[UploadFile],
    save_to_library: bool,
    marks_awarded: Optional[float],
    marks_available: Optional[float],
) -> HandInResponse:
    """A scan or typed answers: keep the pages, then mark them."""
    from .submissions import _marking_response

    openai_client = get_openai_client()
    # Only marking needs the model. A parent who already knows the score is
    # handing in a record, not asking for an opinion, so that should still work.
    if not openai_client and marks_awarded is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Marking is unavailable because OPENAI_API_KEY is not configured. "
                "Add the score yourself to record this without marking."
            ),
        )

    try:
        file_ids, file_contents = await store_uploads(
            db, files, user_id=scope.user_id, session_id=scope.session_id
        )
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))

    page_image_ids = store_page_images(
        db, file_contents, user_id=scope.user_id, session_id=scope.session_id
    )

    extracted = await process_uploaded_files(files, openai_client)

    text_parts: List[str] = []
    if pasted_text.strip():
        text_parts.append(pasted_text.strip())
    for filename, text in extracted.items():
        text_parts.append(f"--- {filename} ---\n{text}")

    student_work = "\n\n".join(text_parts).strip()
    if not student_work:
        raise HTTPException(
            status_code=400,
            detail="Could not read any work from the upload. Try a clearer photo, or type the answers.",
        )

    paper = None
    if save_to_library:
        paper = await _paper_from_completed_work(
            db,
            scope,
            tagged_text=student_work,
            title=title,
            subject=subject,
            file_ids=file_ids,
        )

    # What the paper turned out to be called beats a date stamp, so the record
    # reads "Level 2 Calculator Paper" rather than "Mathematics work, 31 Jul".
    title = title or (paper.title if paper else "") or _fallback_title(subject, done_on)

    assignment = _record_assignment(
        db,
        scope,
        child=child,
        title=title,
        subject=subject,
        paper=paper,
        done_on=done_on,
        minutes=minutes,
        instructions=None,
    )
    db.add(assignment)
    db.flush()

    submission = Submission(
        id=str(uuid.uuid4()),
        assignment_id=assignment.id,
        child_id=child.id,
        minutes_spent=minutes,
        timed=False,
        pause_count=0,
        note=note or None,
        extracted_text=student_work,
        file_ids=file_ids,
        page_image_ids=page_image_ids,
        uploaded_files=[f.filename for f in files if f.filename],
        submitted_at=done_on,
        status="marking",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    def reply(marking) -> HandInResponse:
        return HandInResponse(
            assignmentId=assignment.id,
            submissionId=submission.id,
            childId=child.id,
            subject=subject,
            title=title,
            paperId=paper.id if paper else None,
            savedToLibrary=paper is not None,
            questionCount=len(load_paper_questions(db, paper.id)) if paper else 0,
            marking=_marking_response(db, marking),
        )

    # A score given by hand is the final word; no point asking the model.
    if marks_awarded is not None:
        marking = persist_marking(
            db,
            submission=submission,
            subject=subject,
            paper_id=paper.id if paper else None,
            result=_manual_result(
                marks_awarded=marks_awarded,
                marks_available=marks_available or 0,
                note=note,
            ),
            marked_by="parent",
        )
        assignment.status = "marked"
        db.commit()
        return reply(marking)

    questions = load_paper_questions(db, paper.id) if paper else []
    model = get_reasoning_model()

    try:
        if questions:
            result = mark_per_question(
                questions,
                student_work,
                subject=subject,
                client=openai_client,
                model=model,
                pages=load_page_images(db, page_image_ids),
            )
        else:
            result = mark_holistically(
                student_work,
                subject=subject,
                year_group=child.year_group,
                client=openai_client,
                model=model,
            )
    except Exception as e:
        submission.status = "failed"
        # The work was still handed in, so leave it recorded as done rather than
        # pretending nothing arrived.
        db.commit()
        logger.error(f"Marking failed for hand-in {submission.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Marking failed: {e}")

    marking = persist_marking(
        db,
        submission=submission,
        subject=subject,
        paper_id=paper.id if paper else None,
        result=result,
    )
    assignment.status = "marked"
    db.commit()

    return reply(marking)
