"""
Binary file storage backed by the database.

Uploaded papers and handed-in work are kept as rows in `stored_files` rather
than in object storage, so the app needs no infrastructure beyond the
PostgreSQL instance it already has. Family-scale volume makes this a
reasonable trade: a workbook is tens of kilobytes, a photo of homework a few
megabytes.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models_db import StoredFile

logger = logging.getLogger(__name__)

# Refuse anything larger than this; well above a scanned multi-page paper.
MAX_STORED_FILE_SIZE = 25 * 1024 * 1024


class FileTooLargeError(ValueError):
    """Raised when an upload exceeds MAX_STORED_FILE_SIZE."""


def store_bytes(
    db: Session,
    *,
    content: bytes,
    filename: str,
    content_type: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> StoredFile:
    """
    Persist a file and return the stored row.

    Identical content uploaded again by the same owner reuses the existing row
    rather than duplicating the bytes — re-uploading the same workbook is a
    common thing to do by accident.
    """
    if len(content) > MAX_STORED_FILE_SIZE:
        raise FileTooLargeError(
            f"{filename} is {len(content) / (1024 * 1024):.1f}MB, "
            f"over the {MAX_STORED_FILE_SIZE // (1024 * 1024)}MB limit"
        )

    digest = hashlib.sha256(content).hexdigest()

    existing = (
        db.query(StoredFile)
        .filter(
            StoredFile.sha256 == digest,
            StoredFile.user_id == user_id,
            StoredFile.session_id == session_id,
        )
        .first()
    )
    if existing:
        logger.info(f"Reusing stored file {existing.id} for identical upload {filename}")
        return existing

    stored = StoredFile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=digest,
        content=content,
    )
    db.add(stored)
    db.flush()
    return stored


def get_file(db: Session, file_id: str) -> Optional[StoredFile]:
    """Fetch a stored file by id."""
    return db.query(StoredFile).filter(StoredFile.id == file_id).first()


async def store_uploads(
    db: Session,
    files: List,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Tuple[List[str], Dict[str, bytes]]:
    """
    Persist a list of FastAPI UploadFiles.

    Returns the stored file ids alongside a filename -> bytes map, so the
    caller can run text extraction without re-reading the uploads.
    """
    file_ids: List[str] = []
    contents: Dict[str, bytes] = {}

    for upload in files:
        await upload.seek(0)
        raw = await upload.read()
        if not raw:
            continue

        filename = upload.filename or "upload"
        stored = store_bytes(
            db,
            content=raw,
            filename=filename,
            content_type=upload.content_type,
            user_id=user_id,
            session_id=session_id,
        )
        file_ids.append(stored.id)
        contents[filename] = raw
        # Leave the upload rewound so downstream extraction can read it again.
        await upload.seek(0)

    return file_ids, contents
