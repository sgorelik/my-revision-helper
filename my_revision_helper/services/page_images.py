"""
Keeping the pages of handed-in work as pictures, not only as text.

Transcription loses the things that cannot be written down. On a maths paper the
drawing is often the answer itself — "draw a fully-labelled pie chart" is worth
three marks — and a description of a chart is neither markable with confidence
nor something a child can look at afterwards to see what they got wrong.

So every page of a submission is kept as an image alongside the transcript. The
marker can look at the ones that matter, and the child sees their own work back
next to the marks rather than a paraphrase of it.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..file_processing import PDF_RENDER_SCALE, _render_pdf_page
from .file_store import store_bytes

logger = logging.getLogger(__name__)

# Matches the OCR cap: there is no point keeping pages nothing has read.
MAX_PAGES = 30

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp")


def _page_count(contents: bytes) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(contents)) as pdf:
            return len(pdf.pages)
    except Exception as e:
        logger.warning(f"Could not count PDF pages: {e}")
        return 0


def render_pages(contents: bytes, filename: str) -> List[bytes]:
    """
    The pages of an upload as JPEG images.

    A PDF becomes one image per page. A photo is already a page, so it is kept
    as it is. Anything else has no pages to show.
    """
    lowered = (filename or "").lower()

    if lowered.endswith(".pdf"):
        total = min(_page_count(contents), MAX_PAGES)
        rendered = []
        for index in range(total):
            image = _render_pdf_page(contents, index, scale=PDF_RENDER_SCALE)
            if image:
                rendered.append(image)
        return rendered

    if lowered.endswith(IMAGE_SUFFIXES):
        return [contents]

    return []


def store_page_images(
    db: Session,
    file_contents: Dict[str, bytes],
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> List[str]:
    """
    Render and keep every page of an upload, returning the stored file ids in order.

    Failing to render is not worth losing a hand-in over, so problems are logged
    and the submission goes ahead with whatever pages did work.
    """
    page_ids: List[str] = []

    for filename, contents in (file_contents or {}).items():
        try:
            pages = render_pages(contents, filename)
        except Exception as e:
            logger.warning(f"Could not render pages of {filename}: {e}")
            continue

        base = (filename or "page").rsplit(".", 1)[0]
        for index, image in enumerate(pages, start=1):
            try:
                stored = store_bytes(
                    db,
                    content=image,
                    filename=f"{base} p{index}.jpg",
                    content_type="image/jpeg",
                    user_id=user_id,
                    session_id=session_id,
                )
                page_ids.append(stored.id)
            except Exception as e:
                logger.warning(f"Could not store page {index} of {filename}: {e}")

    if page_ids:
        logger.info(f"Kept {len(page_ids)} page image(s) of the handed-in work")

    return page_ids


def load_page_images(db: Session, page_ids: List[str]) -> List[bytes]:
    """The stored page images, in order, for showing or for marking."""
    from .file_store import get_file

    images: List[bytes] = []
    for page_id in page_ids or []:
        stored = get_file(db, page_id)
        if stored and stored.content:
            images.append(stored.content)
    return images
