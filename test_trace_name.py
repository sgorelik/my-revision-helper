#!/usr/bin/env python3
"""
Test to verify trace names are being set correctly.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_revision_helper.langfuse_client import (
    get_langfuse_client,
    create_trace,
    create_generation,
)

def test_trace_name():
    """Test that trace names are properly set."""
    client = get_langfuse_client()
    if not client:
        print("✗ Langfuse client not initialized")
        return
    
    # Create trace with explicit name
    trace = create_trace(
        name="test-trace-name-verification",
        user_id="test-user",
        revision_id="test-revision",
    )
    
    if not trace:
        print("✗ Failed to create trace")
        return
    
    print(f"✓ Trace created: {trace}")
    print(f"  Trace name should be: test-trace-name-verification")
    
    # Create generation
    generation = create_generation(
        trace=trace,
        name="test-generation-name",
        model="gpt-4o-mini",
        input_data={"test": "input"},
        output="test output",
    )
    
    if generation:
        print(f"✓ Generation created: {generation}")
        print(f"  Generation name should be: test-generation-name")
    
    # End trace
    try:
        trace.end()
        print("✓ Trace ended")
    except Exception as e:
        print(f"⚠ Error ending trace: {e}")
    
    # Flush
    try:
        client.flush()
        print("✓ Flushed")
    except Exception as e:
        print(f"⚠ Error flushing: {e}")
    
    print("\nCheck Langfuse dashboard for:")
    print("  - Trace name: 'test-trace-name-verification'")
    print("  - Generation name: 'test-generation-name'")
    print("  - Input: {'test': 'input'}")
    print("  - Output: 'test output'")

if __name__ == "__main__":
    test_trace_name()

