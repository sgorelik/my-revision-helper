"""
The paper library: work that can be assigned.

Uploading a paper stores the original file, extracts its text, splits off the
answer key and parses the questions. The answer key is kept server-side and is
never included in a response from these endpoints — marking reads it directly
from the database instead.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..file_processing import process_uploaded_files
from ..llm import get_openai_client, get_reasoning_model
from ..models_db import Assignment, Paper, PaperQuestion
from ..schemas.study import (
    BulkUploadItem,
    BulkUploadResponse,
    PaperDetailResponse,
    PaperListItem,
    PaperListResponse,
    PaperQuestionResponse,
    PaperUpdateRequest,
)
from ..subjects import normalise_subject, subject_from_filename, week_from_filename
from ..services.file_store import FileTooLargeError, get_file, store_uploads
from ..services.paper_parser import guess_title, parse_paper
from ..services.worksheet import normalise_resources
from ..services.scope import build_scope, ensure_user_row, restrict_to_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="A database is required for the paper library. Set DATABASE_URL.",
        )
    return db


def _list_item(paper: Paper, question_count: int) -> PaperListItem:
    return PaperListItem(
        id=paper.id,
        title=paper.title,
        subject=paper.subject,
        paperType=paper.paper_type or "workbook",
        topics=paper.topics or [],
        weekLabel=paper.week_label,
        questionCount=question_count,
        totalMarks=paper.total_marks,
        estimatedMinutes=paper.estimated_minutes,
        hasAnswerKey=bool(paper.answer_key_text),
        # An answer key inside the document means the document cannot be handed
        # over as-is; the generated worksheet is used instead.
        originalIsStudentSafe=not paper.answer_key_text,
        resources=normalise_resources(paper.resources),
        parseStatus=paper.parse_status or "pending",
        createdAt=paper.created_at.isoformat() if paper.created_at else "",
    )


async def _create_paper(
    db: Session,
    scope,
    *,
    files: List[UploadFile],
    pasted_text: str = "",
    title: str = "",
    subject: str,
    paper_type: str = "workbook",
    week_label: str = "",
    year_group: str = "",
    resources: Optional[List[Dict[str, str]]] = None,
) -> Paper:
    """
    Store one document and parse it into a paper.

    Shared by the single and bulk upload endpoints. Raises HTTPException for
    problems the caller should report per file, and does not commit: the caller
    decides the transaction boundary, which is what lets a bulk upload keep the
    files that worked.
    """
    try:
        file_ids, _ = await store_uploads(
            db, files, user_id=scope.user_id, session_id=scope.session_id
        )
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))

    openai_client = get_openai_client()
    extracted = await process_uploaded_files(files, openai_client)

    text_parts: List[str] = []
    if pasted_text.strip():
        text_parts.append(pasted_text.strip())
    text_parts.extend(extracted.values())

    full_text = "\n\n".join(text_parts).strip()
    if not full_text:
        raise HTTPException(
            status_code=400,
            detail="Could not read any text from the upload. Supported: docx, pdf, pptx, xlsx, images.",
        )

    parsed = parse_paper(
        full_text,
        subject=subject,
        client=openai_client,
        model=get_reasoning_model() if openai_client else None,
    )

    resolved_title = (
        title.strip()
        or parsed.title
        or guess_title(full_text)
        or next(iter(extracted.keys()), None)
        or f"{subject} paper"
    )

    paper = Paper(
        id=str(uuid.uuid4()),
        user_id=scope.user_id,
        session_id=scope.session_id,
        title=resolved_title,
        subject=subject,
        paper_type=paper_type or "workbook",
        topics=parsed.topics or [],
        week_label=week_label.strip() or None,
        year_group=year_group.strip() or None,
        resources=normalise_resources(resources or []),
        source_file_id=file_ids[0] if file_ids else None,
        full_text=full_text,
        question_text=parsed.question_text,
        answer_key_text=parsed.answer_key_text,
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
                expected_answer=question.expected_answer,
                marking_notes=question.marking_notes,
            )
        )

    logger.info(
        f"Parsed paper {paper.id} ({paper.title}) with {len(parsed.questions)} questions, "
        f"answer key {'found' if parsed.answer_key_text else 'not found'}"
    )
    return paper


@router.post("/papers", response_model=PaperDetailResponse, status_code=201)
async def upload_paper(
    title: str = Form(""),
    subject: str = Form(...),
    paperType: str = Form("workbook"),
    weekLabel: str = Form(""),
    yearGroup: str = Form(""),
    pastedText: str = Form(""),
    # A prerequisite link can be attached at upload time, which is when the
    # parent has the Khan Academy tab open next to the worksheet.
    resourceUrl: str = Form(""),
    resourceLabel: str = Form(""),
    files: List[UploadFile] = File(default_factory=list),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PaperDetailResponse:
    """
    Add a paper to the library.

    Accepts a file upload (docx, pdf, pptx, xlsx, images) or pasted text. The
    document is stored as-is so it can be handed back to the student to work
    from, then parsed into questions.
    """
    db = _require_db(db)

    if not files and not pastedText.strip():
        raise HTTPException(status_code=400, detail="Upload a file or paste the paper text")

    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    paper = await _create_paper(
        db,
        scope,
        files=files,
        pasted_text=pastedText,
        title=title,
        subject=subject,
        paper_type=paperType,
        week_label=weekLabel,
        year_group=yearGroup,
        resources=[{"url": resourceUrl, "label": resourceLabel}] if resourceUrl.strip() else [],
    )

    db.commit()
    db.refresh(paper)

    return await get_paper(paper.id, False, user, db, session_id)


@router.post("/papers/bulk", response_model=BulkUploadResponse)
async def bulk_upload_papers(
    files: List[UploadFile] = File(...),
    # Per-file overrides keyed by filename, as JSON:
    #   {"Maths_Week1.docx": {"subject": "Mathematics", "resourceUrl": "https://…"}}
    # Keyed rather than positional because the browser does not guarantee that
    # the order of a FormData file list survives the round trip.
    meta: str = Form(""),
    subject: str = Form(""),
    weekLabel: str = Form(""),
    yearGroup: str = Form(""),
    paperType: str = Form("workbook"),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> BulkUploadResponse:
    """
    Add many documents at once, one paper per file.

    Setting up a term means uploading a folder of workbooks, so each file becomes
    its own library item with its own parse result. Failures are isolated: a file
    that cannot be read is reported against its own name and does not roll back
    the ones that succeeded.

    Subject and week are inferred from each filename when not given, since
    workbooks are usually named after them.
    """
    db = _require_db(db)

    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file")

    try:
        overrides: Dict[str, Dict[str, str]] = json.loads(meta) if meta.strip() else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="meta was not valid JSON")

    scope = build_scope(user, session_id)
    ensure_user_row(db, user)

    results: List[BulkUploadItem] = []

    for upload in files:
        filename = upload.filename or "upload"
        per_file = overrides.get(filename, {}) if isinstance(overrides, dict) else {}

        resolved_subject = (
            (per_file.get("subject") or "").strip()
            or subject.strip()
            or subject_from_filename(filename)
        )
        if not resolved_subject:
            results.append(
                BulkUploadItem(
                    filename=filename,
                    status="failed",
                    error="Could not tell which subject this is. Set it and retry.",
                )
            )
            continue

        resolved_subject = normalise_subject(resolved_subject) or resolved_subject
        resource_url = (per_file.get("resourceUrl") or "").strip()

        try:
            paper = await _create_paper(
                db,
                scope,
                files=[upload],
                title=(per_file.get("title") or "").strip(),
                subject=resolved_subject,
                paper_type=paperType,
                week_label=(per_file.get("weekLabel") or "").strip()
                or weekLabel.strip()
                or (week_from_filename(filename) or ""),
                year_group=yearGroup,
                resources=(
                    [{"url": resource_url, "label": per_file.get("resourceLabel") or ""}]
                    if resource_url
                    else []
                ),
            )
            # Committed per file so one bad document cannot discard the good ones.
            db.commit()
            db.refresh(paper)

            results.append(
                BulkUploadItem(
                    filename=filename,
                    status="ok",
                    paper=_list_item(
                        paper,
                        db.query(PaperQuestion)
                        .filter(PaperQuestion.paper_id == paper.id)
                        .count(),
                    ),
                )
            )
        except HTTPException as e:
            db.rollback()
            results.append(
                BulkUploadItem(filename=filename, status="failed", error=str(e.detail))
            )
        except Exception as e:
            db.rollback()
            logger.exception(f"Bulk upload failed for {filename}")
            results.append(
                BulkUploadItem(
                    filename=filename, status="failed", error=f"Could not process this file: {e}"
                )
            )

    succeeded = sum(1 for r in results if r.status == "ok")
    logger.info(f"Bulk upload: {succeeded} of {len(results)} files added")

    return BulkUploadResponse(
        items=results, succeeded=succeeded, failed=len(results) - succeeded
    )


@router.get("/papers", response_model=PaperListResponse)
async def list_papers(
    subject: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PaperListResponse:
    """List papers in the library."""
    if db is None:
        return PaperListResponse(items=[], total=0)

    scope = build_scope(user, session_id)
    query = restrict_to_owner(db.query(Paper), Paper, scope)
    if subject:
        query = query.filter(Paper.subject == subject)

    total = query.count()
    papers = query.order_by(Paper.created_at.desc()).offset(offset).limit(limit).all()

    counts = {
        paper.id: db.query(PaperQuestion).filter(PaperQuestion.paper_id == paper.id).count()
        for paper in papers
    }

    return PaperListResponse(
        items=[_list_item(p, counts.get(p.id, 0)) for p in papers],
        total=total,
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
async def get_paper(
    paper_id: str,
    includeText: bool = False,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PaperDetailResponse:
    """
    Fetch a paper with its questions.

    The response contains no answers: PaperQuestionResponse has no field for
    them, and question_text is the answer-key-stripped half of the document.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    paper = restrict_to_owner(db.query(Paper).filter(Paper.id == paper_id), Paper, scope).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    questions = (
        db.query(PaperQuestion)
        .filter(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.order_index)
        .all()
    )

    detail = _list_item(paper, len(questions))
    return PaperDetailResponse(
        **detail.model_dump(),
        questions=[
            PaperQuestionResponse(
                id=q.id,
                number=q.number or str(q.order_index),
                orderIndex=q.order_index,
                questionText=q.question_text,
                sessionLabel=q.session_label,
                band=q.band,
                topic=q.topic,
                marks=q.marks or 1,
            )
            for q in questions
        ],
        questionText=paper.question_text if includeText else None,
        sourceFileId=paper.source_file_id,
        parseError=paper.parse_error,
    )


@router.patch("/papers/{paper_id}", response_model=PaperDetailResponse)
async def update_paper(
    paper_id: str,
    payload: PaperUpdateRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PaperDetailResponse:
    """Correct a paper's metadata after upload."""
    db = _require_db(db)
    scope = build_scope(user, session_id)

    paper = restrict_to_owner(db.query(Paper).filter(Paper.id == paper_id), Paper, scope).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if payload.title is not None:
        paper.title = payload.title.strip() or paper.title
    if payload.subject is not None:
        paper.subject = payload.subject
    if payload.paperType is not None:
        paper.paper_type = payload.paperType
    if payload.weekLabel is not None:
        paper.week_label = payload.weekLabel or None
    if payload.topics is not None:
        paper.topics = payload.topics
    if payload.estimatedMinutes is not None:
        paper.estimated_minutes = payload.estimatedMinutes
    if payload.resources is not None:
        paper.resources = normalise_resources(
            [link.model_dump() for link in payload.resources]
        )

    db.commit()
    return await get_paper(paper_id, False, user, db, session_id)


@router.delete("/papers/{paper_id}")
async def delete_paper(
    paper_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Remove a paper from the library.

    Refuses while assignments still reference it, so a child's assigned work
    cannot silently lose its content.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    paper = restrict_to_owner(db.query(Paper).filter(Paper.id == paper_id), Paper, scope).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    assigned = db.query(Assignment).filter(Assignment.paper_id == paper_id).count()
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"This paper is used by {assigned} assignment(s). Remove those first.",
        )

    db.delete(paper)
    db.commit()
    return {"deleted": True, "paperId": paper_id}


@router.get("/papers/{paper_id}/file")
async def download_paper_file(
    paper_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Download the original uploaded document.

    Note this is the file as supplied, which for a workbook includes its answer
    key. It is available to the account holder, not via any child-facing view.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    paper = restrict_to_owner(db.query(Paper).filter(Paper.id == paper_id), Paper, scope).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not paper.source_file_id:
        raise HTTPException(status_code=404, detail="No original file stored for this paper")

    stored = get_file(db, paper.source_file_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Stored file is missing")

    return Response(
        content=stored.content,
        media_type=stored.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{stored.filename}"'},
    )


@router.post("/papers/{paper_id}/reparse", response_model=PaperDetailResponse)
async def reparse_paper(
    paper_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PaperDetailResponse:
    """
    Re-run parsing on a stored paper.

    Useful when the first attempt happened without an OpenAI key, or when the
    heuristic parse produced a poor split.
    """
    db = _require_db(db)
    scope = build_scope(user, session_id)

    paper = restrict_to_owner(db.query(Paper).filter(Paper.id == paper_id), Paper, scope).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not paper.full_text:
        raise HTTPException(status_code=400, detail="No stored text to re-parse")

    if db.query(Assignment).filter(
        Assignment.paper_id == paper_id, Assignment.status.in_(["submitted", "marked", "done"])
    ).count():
        raise HTTPException(
            status_code=409,
            detail="This paper already has marked work against it; re-parsing would orphan those marks.",
        )

    openai_client = get_openai_client()
    parsed = parse_paper(
        paper.full_text,
        subject=paper.subject,
        client=openai_client,
        model=get_reasoning_model() if openai_client else None,
    )

    db.query(PaperQuestion).filter(PaperQuestion.paper_id == paper.id).delete()

    paper.question_text = parsed.question_text
    paper.answer_key_text = parsed.answer_key_text
    paper.total_marks = parsed.total_marks
    paper.estimated_minutes = parsed.estimated_minutes or paper.estimated_minutes
    paper.topics = parsed.topics or paper.topics
    paper.parse_status = parsed.parse_status
    paper.parse_error = parsed.parse_error
    paper.parsed_at = datetime.utcnow()

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
                expected_answer=question.expected_answer,
                marking_notes=question.marking_notes,
            )
        )

    db.commit()
    logger.info(f"Re-parsed paper {paper.id}: {len(parsed.questions)} questions")
    return await get_paper(paper_id, False, user, db, session_id)
