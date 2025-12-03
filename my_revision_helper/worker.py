"""
Temporal worker entrypoint for the My Revision Helper.

Run this worker to host workflows and activities defined in this package.

The worker:
- Connects to a Temporal server
- Registers workflows and activities
- Polls for tasks and executes them
- Handles retries, timeouts, and state management

Usage:
    python -m my_revision_helper.worker

Environment Variables:
    TEMPORAL_TARGET: Temporal server address (default: localhost:7233)
    TEMPORAL_TASK_QUEUE: Task queue name (default: revision-helper-queue)

Note:
    The worker must be running for workflows to execute. In production, run
    multiple worker instances for high availability and load distribution.
"""

from __future__ import annotations

import asyncio
import os

try:
    from temporalio.client import Client  # type: ignore
    from temporalio.worker import Worker  # type: ignore
except Exception:  # pragma: no cover - allows project to exist without Temporal installed
    Client = None  # type: ignore
    Worker = None  # type: ignore

from . import activities, workflows


async def run_worker() -> None:
    """Connect to Temporal and run the worker."""
    if Client is None or Worker is None:
        raise RuntimeError(
            "Temporal SDK not installed. Install with `pip install temporalio`."
        )

    target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "revision-helper-queue")

    client = await Client.connect(target)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[workflows.RevisionWorkflow],
        activities=[activities.create_revision_task],
    )

    print(f"Starting worker on {target} with task queue '{task_queue}'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())


