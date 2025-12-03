"""
Temporal workflows for the My Revision Helper.

This file defines long-running orchestrations that call activities in
`activities.py`. Wire these up to your Temporal worker in `worker.py`.

Workflows are durable, stateful functions that orchestrate activities.
They provide:
- Automatic retries for failed activities
- Timeout handling
- State persistence across restarts
- Query and signal capabilities

Current State:
    The RevisionWorkflow is a basic implementation that creates revision tasks.
    Future iterations will expand this to handle question generation and marking
    as separate workflow steps.

Usage:
    Workflows are started by the FastAPI backend when revisions are created.
    They run on the Temporal worker and can be queried/signaled for state updates.
"""

from __future__ import annotations

from datetime import datetime

from . import activities
from .models import RevisionTask

try:
    # Temporal Python SDK is optional at this stage; import lazily.
    from temporalio import workflow  # type: ignore
except Exception:  # pragma: no cover - allows project to run without Temporal installed
    workflow = None  # type: ignore


if workflow is not None:

    @workflow.defn
    class RevisionWorkflow:
        """
        Workflow that creates and processes a revision task.

        This workflow orchestrates the creation of a revision. Currently it:
        1. Calls the create_revision_task activity
        2. Returns a RevisionTask with the result

        Future enhancements:
        - Question generation workflow
        - Answer marking workflow
        - Session state management
        """

        @workflow.run
        async def run(
            self, task_id: str, title: str, description: str | None = None
        ) -> RevisionTask:
            """
            Execute the revision workflow.

            Args:
                task_id: Unique identifier for this revision task
                title: Name/title of the revision
                description: Optional description of what to study

            Returns:
                RevisionTask with the created task details

            Note:
                The activity has a 60-second timeout. If it fails or times out,
                Temporal will retry according to the workflow's retry policy.
            """
            now = workflow.now()
            result = await workflow.execute_activity(
                activities.create_revision_task,
                title,
                description,
                start_to_close_timeout=workflow.timedelta(seconds=60),
            )
            return RevisionTask(
                id=task_id,
                title=result.get("task_name", title),
                created_at=datetime.fromisoformat(now.isoformat()),
                metadata=result,
            )


__all__ = ["RevisionWorkflow"]


