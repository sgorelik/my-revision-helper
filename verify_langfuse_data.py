#!/usr/bin/env python3
"""
Verify that data is actually being sent to Langfuse correctly.
This script creates a trace with observation and checks what's actually being sent.
"""

import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_revision_helper.langfuse_client import (
    get_langfuse_client,
    create_trace,
    create_generation,
)

def verify_langfuse_data():
    """Create a trace and verify the data structure being sent."""
    print("=" * 60)
    print("Verifying Langfuse Data Structure")
    print("=" * 60)
    
    client = get_langfuse_client()
    if not client:
        print("✗ Langfuse client not initialized")
        return False
    
    print("✓ Langfuse client initialized")
    
    # Create trace
    trace_name = "verify-data-structure-test"
    trace = create_trace(
        name=trace_name,
        user_id="verify-user",
        revision_id="verify-revision",
    )
    
    if not trace:
        print("✗ Failed to create trace")
        return False
    
    print(f"✓ Trace created: {trace}")
    print(f"  Trace name: {trace_name}")
    print(f"  Trace type: {type(trace)}")
    
    # Check trace attributes
    print("\nTrace attributes:")
    for attr in dir(trace):
        if not attr.startswith('_'):
            try:
                value = getattr(trace, attr)
                if not callable(value):
                    print(f"  {attr}: {value}")
            except:
                pass
    
    # Create generation with test data
    test_input = {
        "messages": [
            {"role": "system", "content": "You are a test assistant"},
            {"role": "user", "content": "Say hello"}
        ]
    }
    test_output = "Hello! This is a test response."
    
    print(f"\nCreating generation with:")
    print(f"  Input: {json.dumps(test_input, indent=2)}")
    print(f"  Output: {test_output}")
    
    generation = create_generation(
        trace=trace,
        name="verify-generation",
        model="gpt-4o-mini",
        input_data=test_input,
        output=test_output,
        metadata={"test": True, "verification": "data-structure"},
    )
    
    if not generation:
        print("✗ Failed to create generation")
        return False
    
    print(f"\n✓ Generation created: {generation}")
    print(f"  Generation type: {type(generation)}")
    
    # Check generation attributes
    print("\nGeneration attributes:")
    for attr in dir(generation):
        if not attr.startswith('_'):
            try:
                value = getattr(generation, attr)
                if not callable(value):
                    print(f"  {attr}: {value}")
            except:
                pass
    
    # Try to get the actual data from the generation object
    print("\nAttempting to inspect generation data:")
    try:
        # Check if there's a way to get the data
        if hasattr(generation, 'id'):
            print(f"  Generation ID: {generation.id}")
        if hasattr(generation, 'trace_id'):
            print(f"  Trace ID: {generation.trace_id}")
    except Exception as e:
        print(f"  Could not inspect: {e}")
    
    # End trace
    try:
        trace.end()
        print("\n✓ Trace ended")
    except Exception as e:
        print(f"\n⚠ Error ending trace: {e}")
    
    # Flush
    try:
        client.flush()
        print("✓ Client flushed")
    except Exception as e:
        print(f"⚠ Error flushing: {e}")
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print("\nPlease check your Langfuse dashboard for:")
    print(f"  - Trace name: '{trace_name}'")
    print(f"  - Generation name: 'verify-generation'")
    print(f"  - Look at the OBSERVATION (not the trace) for input/output")
    print("\nIf input/output are still empty, the issue is with how")
    print("the data is being serialized or sent to Langfuse.")
    print()
    
    return True

if __name__ == "__main__":
    verify_langfuse_data()

