#!/usr/bin/env python3
"""
Test script to verify that input and output are being properly set in Langfuse.
This creates a test trace with a generation that has explicit input/output.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_revision_helper.langfuse_client import (
    get_langfuse_client,
    create_trace,
    create_generation,
)

def test_input_output():
    """Test that input and output are properly recorded."""
    print("=" * 60)
    print("Testing Input/Output Recording")
    print("=" * 60)
    
    client = get_langfuse_client()
    if not client:
        print("✗ FAILED: Langfuse client not initialized")
        return False
    
    # Create a trace
    trace = create_trace(
        name="test-input-output",
        user_id="test-user",
        revision_id="test-revision",
        run_id="test-run",
    )
    
    if not trace:
        print("✗ FAILED: Could not create trace")
        return False
    
    print("✓ Trace created")
    
    # Create a generation with explicit input/output
    test_input = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is 2+2?"}
        ]
    }
    test_output = "2+2 equals 4"
    
    print(f"Creating generation with input: {test_input}")
    print(f"Output: {test_output}")
    
    generation = create_generation(
        trace=trace,
        name="test-generation-with-data",
        model="gpt-4o-mini",
        input_data=test_input,
        output=test_output,
        metadata={"test": True, "temperature": 0.7},
    )
    
    if not generation:
        print("✗ FAILED: Could not create generation")
        return False
    
    print("✓ Generation created")
    
    # End the trace
    try:
        trace.end()
        print("✓ Trace ended")
    except Exception as e:
        print(f"⚠ Warning: Could not end trace: {e}")
    
    # Flush
    try:
        client.flush()
        print("✓ Client flushed")
    except Exception as e:
        print(f"⚠ Warning: Could not flush: {e}")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
    print("Check your Langfuse dashboard for trace 'test-input-output'")
    print("The generation 'test-generation-with-data' should have:")
    print("  - Input: A messages array with system and user messages")
    print("  - Output: '2+2 equals 4'")
    print()
    
    return True

if __name__ == "__main__":
    test_input_output()

