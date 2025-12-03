"""
Interactive client helper for inspecting or interacting with workflows.

You can extend this to:
  - Query workflow state
  - Signal workflows
  - List active workflows, etc.
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


async def show_workflow_result(workflow_id: str) -> None:
    if Client is None:
        raise RuntimeError(
            "Temporal SDK not installed. Install with `pip install temporalio`."
        )

    target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
    client = await Client.connect(target)

    handle = client.get_workflow_handle(workflow_id)
    result = await handle.result()
    print(f"Workflow result for '{workflow_id}': {result}")


def main(argv: Sequence[str] | None = None) -> None:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print("Usage: client_interact.py <workflow_id>")
        raise SystemExit(1)
    asyncio.run(show_workflow_result(argv[0]))


if __name__ == "__main__":
    main()


