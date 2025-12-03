"""
Data models and shared data structures for the My Revision Helper project.

This module defines core domain models used across workflows and activities.
These models represent the business entities in the revision system.

Note: The HTTP API layer (`api.py`) uses separate Pydantic models for request/response
validation. These models are used internally by Temporal workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class RevisionTask:
    """
    Represents a single revision task tracked by the assistant.

    This model is used by Temporal workflows to represent a revision task.
    It contains the core metadata about a revision that workflows operate on.

    Attributes:
        id: Unique identifier for the revision task
        title: Name/title of the revision
        created_at: Timestamp when the task was created
        metadata: Optional dictionary containing additional task metadata
                  (e.g., AI suggestions, workflow state)
    """

    id: str
    title: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


__all__ = ["RevisionTask"]


