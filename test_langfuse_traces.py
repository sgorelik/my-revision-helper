#!/usr/bin/env python3
"""
Test script to verify Langfuse traces are being created and sent.
This will create a test trace and generation to verify the integration is working.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from my_revision_helper.langfuse_client import (
    get_langfuse_client,
    create_trace,
    create_generation,
)

def test_langfuse_traces():
    """Test creating and sending traces to Langfuse."""
    print("=" * 80)
    print("Testing Langfuse Trace Creation")
    print("=" * 80)
    
    # Check if Langfuse is configured
    client = get_langfuse_client()
    if not client:
        print("❌ FAILED: Langfuse client not initialized")
        print("   Check your LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables")
        return False
    
    print("✓ Langfuse client initialized")
    
    # Create a test trace
    print("\nCreating test trace...")
    trace = create_trace(
        name="test-trace",
        user_id="test-user-123",
        revision_id="test-revision-456",
        run_id="test-run-789",
        metadata={"test": True, "source": "test_script"},
    )
    
    if not trace:
        print("❌ FAILED: Could not create trace")
        return False
    
    print("✓ Trace created")
    
    # Create a test generation
    print("\nCreating test generation...")
    generation = create_generation(
        trace=trace,
        name="test-generation",
        model="gpt-4o-mini",
        input_data={"test": "input"},
        output="test output",
        metadata={"test": True},
    )
    
    if not generation:
        print("❌ FAILED: Could not create generation")
        return False
    
    print("✓ Generation created")
    
    # Final flush
    print("\nFlushing client...")
    try:
        client.flush()
        print("✓ Client flushed successfully")
    except Exception as e:
        print(f"⚠ WARNING: Flush failed: {e}")
    
    print("\n" + "=" * 80)
    print("✅ Test completed successfully!")
    print("=" * 80)
    print("\nCheck your Langfuse dashboard for the test trace:")
    print("  - Trace name: 'test-trace'")
    print("  - User ID: 'test-user-123'")
    print("  - Revision ID: 'test-revision-456'")
    print("\nIf you don't see it, check:")
    print("  1. Your Langfuse credentials are correct")
    print("  2. Your network connection")
    print("  3. Langfuse service status")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    success = test_langfuse_traces()
    sys.exit(0 if success else 1)

