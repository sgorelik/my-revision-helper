"""
AI context helpers.

These functions are used by services/routers to build prompts without needing
to import the FastAPI module.
"""

from __future__ import annotations

import os
import logging

from .langfuse_client import fetch_prompt

logger = logging.getLogger(__name__)


def get_prep_check_context() -> str:
    """
    Get general context/instructions specifically for prep checking.

    Tries to fetch from Langfuse first, then falls back to PREP_CHECK_CONTEXT env var or default.
    """
    langfuse_prompt_data = fetch_prompt("general-context-prep-check")
    if langfuse_prompt_data and langfuse_prompt_data.get("prompt"):
        context = langfuse_prompt_data["prompt"]
        logger.info("Using general-context-prep-check prompt from Langfuse")
        return context

    return os.getenv(
        "PREP_CHECK_CONTEXT",
        (
            "You are a helpful AI tutor reviewing student prep work. "
            "CRITICAL RULES:\n"
            "- NEVER provide correct answers or solutions\n"
            "- NEVER give away the answer to a question\n"
            "- You can identify that an answer is wrong, but you must NOT tell them what the right answer is\n"
            "- Focus on process, methodology, and improvement areas\n\n"
            "Your role is to:\n"
            "- Identify areas that need improvement\n"
            "- Point out specific errors (calculation, spelling, grammar, etc.)\n"
            "- Reiterate rubrics and requirements\n"
            "- Guide students toward finding the answer themselves\n"
            "- Encourage showing work and providing evidence"
        ),
    )

