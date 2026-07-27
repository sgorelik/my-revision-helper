"""
Shared OpenAI client access.

Lives outside api.py so services and routers can reach the model without
importing the API module (which imports them in turn).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - SDK is optional at import time
    OpenAI = None  # type: ignore

VALID_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]

DEFAULT_MODEL = "gpt-4o-mini"


def get_openai_client() -> Optional[Any]:
    """Return an OpenAI client if the SDK and API key are available."""
    if OpenAI is None:
        logger.warning("OpenAI SDK not installed")
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY environment variable not set")
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to create OpenAI client: {e}", exc_info=True)
        return None


def get_openai_model() -> str:
    """Get the OpenAI model name from env, with a safe fallback."""
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    if model not in VALID_MODELS:
        logger.warning(
            f"Model '{model}' may not be valid. Falling back to '{DEFAULT_MODEL}'. "
            f"Valid models include: {', '.join(VALID_MODELS)}"
        )
        return DEFAULT_MODEL
    return model


def get_reasoning_model() -> str:
    """
    Model used for the heavier structured tasks: parsing a workbook into
    questions, and marking a completed paper against its answer key.

    These run once per document rather than once per interaction, so the
    accuracy is worth more than the token cost.
    """
    return os.getenv("OPENAI_PARSING_MODEL", "gpt-4o")
