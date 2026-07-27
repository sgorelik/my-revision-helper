from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class PrepCheckResponse(BaseModel):
    """Response from prep check endpoint."""

    feedback: str
    prepCheckId: str
    approxScore: Optional[int] = None
    assessedAt: Optional[str] = None


class PrepCheckListItem(BaseModel):
    id: str
    subject: str
    createdAt: str
    assessedAt: Optional[str] = None
    approxScore: Optional[int] = None
    preview: Optional[str] = None
    uploadedFilesCount: int = 0


class PrepCheckListResponse(BaseModel):
    items: List[PrepCheckListItem]
    total: int


class PrepCheckDetailResponse(BaseModel):
    id: str
    subject: str
    description: Optional[str] = None
    prepWorkText: str
    uploadedFiles: List[str] = []
    feedback: str
    approxScore: Optional[int] = None
    assessedAt: Optional[str] = None
    previousPrepCheckId: Optional[str] = None
    createdAt: str

