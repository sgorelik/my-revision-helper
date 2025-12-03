#!/usr/bin/env python3
"""Quick bootstrap test to verify the setup is working."""

import asyncio
import os
import sys

async def test_bootstrap():
    """Test that all components are properly set up.

    Note: This coroutine is invoked via the sync wrapper
    ``test_bootstrap_pytest`` so that pytest does not need an async plugin.
    """
    print("🧪 Testing My Revision Helper Bootstrap...")
    print()
    
    # Test 1: Package imports
    print("1. Testing package imports...")
    try:
        from my_revision_helper import activities, workflows, worker, models
        print("   ✓ All modules import successfully")
    except Exception as e:
        print(f"   ✗ Import failed: {e}")
        return False
    
    # Test 2: Environment variables
    print("2. Testing environment variables...")
    temporal_target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "revision-helper-queue")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    print(f"   ✓ TEMPORAL_TARGET: {temporal_target}")
    print(f"   ✓ TEMPORAL_TASK_QUEUE: {task_queue}")
    if openai_key:
        print(f"   ✓ OPENAI_API_KEY: {'*' * 10}...{openai_key[-4:]}")
    else:
        print("   ⚠ OPENAI_API_KEY: Not set")
    
    # Test 3: Temporal connection
    print("3. Testing Temporal server connection...")
    try:
        from temporalio.client import Client
        client = await Client.connect(temporal_target)
        print(f"   ✓ Successfully connected to Temporal at {temporal_target}")
        # Close connection
        # Note: Client doesn't have close(), connection will close automatically
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        print("   ℹ Make sure Temporal server is running: temporal server start-dev")
        return False
    
    # Test 4: Activity registration
    print("4. Testing activity registration...")
    try:
        activity = activities.create_revision_task
        print("   ✓ Activity is properly defined")
    except Exception as e:
        print(f"   ✗ Activity check failed: {e}")
        return False
    
    print()
    print("✅ All bootstrap tests passed!")
    print()
    print("Next steps:")
    print("  1. Start the worker: uv run python -m my_revision_helper.worker")
    print("  2. In another terminal, start the CLI: uv run python -m my_revision_helper.cli")
    return True


def test_bootstrap_pytest():
    """Sync wrapper so pytest can run the async bootstrap test."""
    success = asyncio.run(test_bootstrap())
    assert success is True


# Prevent pytest from trying to treat the async function itself as a test
test_bootstrap.__test__ = False  # type: ignore[attr-defined]

if __name__ == "__main__":
    success = asyncio.run(test_bootstrap())
    sys.exit(0 if success else 1)

