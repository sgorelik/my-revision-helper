"""
Activities module for the My Revision Helper project.

Activities are the units of work that can be retried independently and
orchestrated by workflows. They represent the actual business logic operations.

Key Characteristics:
- Activities are idempotent (safe to retry)
- They can call external services (OpenAI, databases, etc.)
- Temporal automatically retries them on failure
- They have configurable timeouts

Current Activities:
- create_revision_task: Creates a revision with optional AI enhancement

Future Activities:
- generate_questions: Generate questions using AI
- mark_answer: Evaluate student answers using AI
- process_uploaded_files: Extract content from uploaded files
"""

from __future__ import annotations

import os
from typing import Any

try:
    from openai import OpenAI  # type: ignore
    from temporalio import activity  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore
    activity = None  # type: ignore


if activity is not None:

    @activity.defn
    async def create_revision_task(
        task_name: str, description: str | None = None
    ) -> dict[str, Any]:
        """
        Create a revision task activity.

        This activity handles the creation of a revision task and can optionally
        use OpenAI to enhance the task with suggestions or study plans.

        Args:
            task_name: Name/title of the revision task
            description: Optional description of what to study

        Returns:
            Dictionary containing:
            - task_name: The task name
            - description: The description (if provided)
            - status: "created"
            - ai_suggestions: Optional AI-generated study plan (if OpenAI available)
            - ai_error: Optional error message if AI call failed

        Note:
            If OpenAI is configured and available, this activity will attempt to
            generate study suggestions. If the AI call fails, the activity still
            succeeds (the error is stored in ai_error), ensuring the workflow
            doesn't fail due to external service issues.
        """
        result = {
            "task_name": task_name,
            "description": description,
            "status": "created",
        }

        # Optionally enhance with OpenAI if API key is available
        if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
            try:
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful study assistant. Provide brief, actionable revision suggestions.",
                        },
                        {
                            "role": "user",
                            "content": f"Create a study plan for: {task_name}. {description or ''}",
                        },
                    ],
                    max_tokens=200,
                    temperature=0.7,
                )
                result["ai_suggestions"] = response.choices[0].message.content
            except Exception as e:
                # Don't fail the workflow if OpenAI call fails
                result["ai_error"] = str(e)

        return result


else:
    # Fallback if temporalio is not available
    async def create_revision_task(task_name: str, description: str | None = None) -> dict[str, Any]:
        return {"task_name": task_name, "description": description, "status": "created"}


async def example_activity(task_name: str, payload: dict[str, Any] | None = None) -> str:
    """
    Example activity implementation.

    Kept for backward compatibility.
    """
    if payload:
        description = payload.get("description")
        result = await create_revision_task(task_name, description)
        return f"Created revision task: {result.get('task_name', task_name)}"
    return f"Handled task '{task_name}' with payload={payload!r}"


__all__ = ["example_activity", "create_revision_task"]


