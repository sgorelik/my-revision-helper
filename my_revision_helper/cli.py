"""
Interactive command-line interface for entering and managing revision tasks.

Usage:
    python -m my_revision_helper.cli
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Sequence

try:
    from temporalio.client import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore

from .workflows import RevisionWorkflow


class RevisionCLI:
    """Simple CLI for managing revision tasks."""

    def __init__(self) -> None:
        self.target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
        self.task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "revision-helper-queue")
        self.client: Client | None = None

    async def connect(self) -> None:
        """Connect to Temporal server."""
        if Client is None:
            raise RuntimeError(
                "Temporal SDK not installed. Install with `pip install temporalio`."
            )
        self.client = await Client.connect(self.target)
        print(f"✓ Connected to Temporal at {self.target}")

    async def add_task(self, title: str) -> str:
        """Add a new task and return the workflow ID."""
        if self.client is None:
            await self.connect()

        task_id = str(uuid.uuid4())[:8]  # Short ID for readability

        handle = await self.client.start_workflow(
            RevisionWorkflow.run,
            task_id,
            title,
            id=task_id,
            task_queue=self.task_queue,
        )

        print(f"✓ Task added! ID: {handle.id}")
        return handle.id

    async def list_tasks(self) -> None:
        """List recent workflows (simplified - just shows message)."""
        if self.client is None:
            await self.connect()

        # Note: Full workflow listing requires more complex queries
        # This is a placeholder for future enhancement
        print("Task listing feature - coming soon!")
        print("(For now, tasks are tracked by their workflow IDs)")

    def print_help(self) -> None:
        """Print help message."""
        print("\nCommands:")
        print("  add <task>     - Add a new task")
        print("  list           - List tasks (coming soon)")
        print("  help           - Show this help message")
        print("  quit / exit    - Exit the CLI")
        print()

    async def run_interactive(self) -> None:
        """Run the interactive CLI loop."""
        await self.connect()
        print("\n" + "=" * 50)
        print("My Revision Helper CLI")
        print("=" * 50)
        self.print_help()

        while True:
            try:
                user_input = input("> ").strip()

                if not user_input:
                    continue

                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()

                if command in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break
                elif command == "help":
                    self.print_help()
                elif command == "add":
                    if len(parts) < 2:
                        print("Error: Please provide a task title")
                        print("Usage: add <task title>")
                        continue
                    await self.add_task(parts[1])
                elif command == "list":
                    await self.list_tasks()
                else:
                    # If no command matches, treat the whole input as a task
                    await self.add_task(user_input)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


async def main_async() -> None:
    """Main async entry point."""
    cli = RevisionCLI()
    await cli.run_interactive()


def main(argv: Sequence[str] | None = None) -> None:
    """Main entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()


