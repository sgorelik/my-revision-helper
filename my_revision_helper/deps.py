"""
FastAPI dependency helpers (small, composable).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Cookie, Request


def get_session_id(request: Request, session_id: Optional[str] = Cookie(None)) -> str:
    """Get or generate session ID for anonymous users."""
    if not session_id:
        # Prefer middleware-generated ID (if any) so it matches Set-Cookie.
        return getattr(request.state, "session_id", None) or str(uuid.uuid4())
    return session_id

