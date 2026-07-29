from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..deps import get_session_id
from ..llm import get_openai_model
from ..storage import StorageAdapter
from ..services.prep_check_service import run_prep_check
from ..ai_context import get_prep_check_context
from ..langfuse_client import fetch_prompt, render_prompt, create_trace, create_generation, get_langfuse
from ..schemas.prep_check import PrepCheckResponse, PrepCheckListResponse, PrepCheckDetailResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


@router.post("/prep-check", response_model=PrepCheckResponse)
async def check_prep(
    subject: str = Form(...),
    description: str = Form(""),
    files: List[UploadFile] = File(default_factory=list),
    previousPrepCheckId: Optional[str] = Form(None),
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    from fastapi import HTTPException

    if not OpenAI:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    # Validate that we have either files or description
    if not files and not description:
        raise HTTPException(
            status_code=400,
            detail="Please provide either uploaded files or a description of the prep work",
        )

    try:
        result = await run_prep_check(
            subject=subject,
            description=description,
            files=files,
            previous_prep_check_id=previousPrepCheckId,
            user=user,
            db=db,
            session_id=session_id,
            openai_cls=OpenAI,
            openai_api_key=os.getenv("OPENAI_API_KEY") or "",
            openai_model=get_openai_model(),
            prompt_general_context=get_prep_check_context(),
            fetch_prompt=fetch_prompt,
            render_prompt=render_prompt,
            create_trace=create_trace,
            create_generation=create_generation,
            get_langfuse=get_langfuse,
        )
        return PrepCheckResponse(
            feedback=result.feedback,
            prepCheckId=result.prep_check_id,
            approxScore=result.approx_score,
            assessedAt=result.assessed_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error checking prep work: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check prep work: {str(e)}")


@router.get("/prep-checks", response_model=PrepCheckListResponse)
async def list_prep_checks(
    limit: int = 20,
    offset: int = 0,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PrepCheckListResponse:
    # Basic bounds to avoid pathological requests
    limit = max(1, min(50, limit))
    offset = max(0, offset)

    storage = StorageAdapter(user, db, session_id)
    data = storage.list_prep_checks(limit=limit, offset=offset)
    return PrepCheckListResponse(**data)


@router.get("/prep-checks/{prep_check_id}", response_model=PrepCheckDetailResponse)
async def get_prep_check(
    prep_check_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> PrepCheckDetailResponse:
    from fastapi import HTTPException

    storage = StorageAdapter(user, db, session_id)
    pc = storage.get_prep_check(prep_check_id)
    if not pc:
        raise HTTPException(status_code=404, detail="Prep check not found")
    return PrepCheckDetailResponse(**pc)

