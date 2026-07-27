"""
Ownership scoping for the study programme.

The app follows the existing convention: an authenticated parent owns rows via
`user_id`, an anonymous visitor via a `session_id` cookie. Children are
profiles under that owner rather than accounts of their own, so every child
lookup is filtered by the owner before anything else happens. That single check
is what stops one family's data being reachable from another's session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Query, Session

from ..models_db import Child

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scope:
    """Who is making the request."""

    user_id: Optional[str]
    session_id: Optional[str]

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


def build_scope(user: Optional[Dict[str, str]], session_id: Optional[str]) -> Scope:
    """Resolve the caller into a Scope."""
    if user and user.get("user_id"):
        return Scope(user_id=user["user_id"], session_id=None)
    return Scope(user_id=None, session_id=session_id)


def ensure_user_row(db: Session, user: Optional[Dict[str, str]]) -> None:
    """Create the users row on first write, so foreign keys resolve."""
    if not user or not user.get("user_id"):
        return
    from ..storage import get_or_create_user

    get_or_create_user(db, user["user_id"], user.get("email"), user.get("name"))


def restrict_to_owner(query: Query, model, scope: Scope) -> Query:
    """Filter a query down to rows the caller owns."""
    if scope.is_authenticated:
        return query.filter(model.user_id == scope.user_id)
    return query.filter(model.session_id == scope.session_id)


def owner_columns(scope: Scope) -> Dict[str, Optional[str]]:
    """Owner column values to set when creating a row."""
    return {"user_id": scope.user_id, "session_id": scope.session_id}


def get_owned_child(db: Session, child_id: str, scope: Scope) -> Optional[Child]:
    """
    Fetch a child only if the caller owns them.

    Returns None rather than raising so callers can decide between a 404 and a
    quiet empty result.
    """
    if not child_id:
        return None
    query = db.query(Child).filter(Child.id == child_id)
    return restrict_to_owner(query, Child, scope).first()
