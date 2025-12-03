"""
Simple client script to start a new RevisionWorkflow run.

Usage (after Temporal server and worker are running):

    python -m my_revision_helper.client_start "task-id-123" "My revision task"
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Sequence

try:
    from temporalio.client import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore

from .workflows import RevisionWorkflow


async def start_workflow(task_id: str, title: str) -> None:
    if Client is None:
        raise RuntimeError(
            "Temporal SDK not installed. Install with `pip install temporalio`."
        )

    target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "revision-helper-queue")

    client = await Client.connect(target)

    handle = await client.start_workflow(
        RevisionWorkflow.run,
        task_id,
        title,
        id=task_id,
        task_queue=task_queue,
    )

    print(f"Started workflow with id={handle.id}, run_id={handle.result_run_id}")


def main(argv: Sequence[str] | None = None) -> None:
    argv = list(argv or sys.argv[1:])
    if len(argv) < 2:
        print("Usage: client_start.py <task_id> <title>")
        raise SystemExit(1)
    asyncio.run(start_workflow(argv[0], argv[1]))


if __name__ == "__main__":
    main()


