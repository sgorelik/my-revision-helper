"""
In-memory storage for the MVP.

This module intentionally contains the in-memory dictionaries used when the app
is running without a database.

Why this exists:
- `StorageAdapter` needs an in-memory backend when `DATABASE_URL` is not set.
- The storage layer should NOT depend on the web layer (`api.py`).

Do NOT put request-handling logic here. Keep it as pure state containers.
"""

from __future__ import annotations

from typing import Dict, List

# Stored revision definitions keyed by revision_id
# Each entry contains: id, name, subject, topics, description, desiredQuestionCount,
# accuracyThreshold, extractedTexts, etc.
REVISION_DEFS: Dict[str, dict] = {}

# Stored runs keyed by run_id
# Each entry contains: id, revisionId, status, etc.
REVISION_RUNS: Dict[str, dict] = {}

# Per-run questions and answers
# RUN_QUESTIONS[run_id] = [{"id": "...", "text": "..."}, ...]
# RUN_ANSWERS[run_id] = [AnswerResult dict, ...]
RUN_QUESTIONS: Dict[str, List[dict]] = {}
RUN_ANSWERS: Dict[str, List[dict]] = {}

