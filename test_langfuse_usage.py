#!/usr/bin/env python3
"""
Test script to verify Langfuse is being used in production.
This will check:
1. If Langfuse client is initialized
2. If traces are being created
3. If generations are being logged
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
    get_langfuse_environment,
)

def test_langfuse_initialization():
    """Test if Langfuse client can be initialized."""
    print("=" * 60)
    print("Testing Langfuse Initialization")
    print("=" * 60)
    
    # Check environment variables
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    environment = os.getenv("LANGFUSE_ENVIRONMENT", "production")
    
    print(f"LANGFUSE_PUBLIC_KEY: {'SET' if public_key else 'NOT SET'}")
    print(f"LANGFUSE_SECRET_KEY: {'SET' if secret_key else 'NOT SET'}")
    print(f"LANGFUSE_HOST: {host}")
    print(f"LANGFUSE_ENVIRONMENT: {environment}")
    print()
    
    # Try to get client
    client = get_langfuse_client()
    if client:
        print("✓ Langfuse client initialized successfully")
        return client
    else:
        print("✗ FAILED: Langfuse client not initialized")
        return None

def test_trace_creation(client):
    """Test if we can create a trace."""
    print("=" * 60)
    print("Testing Trace Creation")
    print("=" * 60)
    
    if not client:
        print("✗ SKIPPED: No Langfuse client")
        return None
    
    try:
        trace = create_trace(
            name="test-trace",
            user_id="test-user-123",
            revision_id="test-revision-456",
            run_id="test-run-789",
            metadata={"test": True}
        )
        
        if trace:
            print("✓ Trace created successfully")
            print(f"  Trace name: test-trace")
            print(f"  User ID: test-user-123")
            print(f"  Revision ID: test-revision-456")
            return trace
        else:
            print("✗ FAILED: Trace creation returned None")
            return None
    except Exception as e:
        print(f"✗ FAILED: Error creating trace: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_generation_logging(trace):
    """Test if we can log a generation."""
    print("=" * 60)
    print("Testing Generation Logging")
    print("=" * 60)
    
    if not trace:
        print("✗ SKIPPED: No trace available")
        return False
    
    try:
        generation = create_generation(
            trace=trace,
            name="test-generation",
            model="gpt-4o-mini",
            input_data={"messages": [{"role": "user", "content": "Test message"}]},
            output="Test response",
            metadata={"temperature": 0.7}
        )
        
        if generation:
            print("✓ Generation logged successfully")
            print(f"  Generation name: test-generation")
            print(f"  Model: gpt-4o-mini")
            return True
        else:
            print("✗ FAILED: Generation logging returned None")
            return False
    except Exception as e:
        print(f"✗ FAILED: Error logging generation: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_flush(client):
    """Test if we can flush the client."""
    print("=" * 60)
    print("Testing Client Flush")
    print("=" * 60)
    
    if not client:
        print("✗ SKIPPED: No Langfuse client")
        return False
    
    try:
        client.flush()
        print("✓ Client flushed successfully")
        print("  Note: Traces should now be visible in Langfuse dashboard")
        return True
    except Exception as e:
        print(f"✗ FAILED: Error flushing client: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Langfuse Usage Test")
    print("=" * 60 + "\n")
    
    # Test initialization
    client = test_langfuse_initialization()
    print()
    
    if not client:
        print("\n" + "=" * 60)
        print("SUMMARY: Langfuse is NOT configured properly")
        print("=" * 60)
        print("\nPlease check:")
        print("1. LANGFUSE_PUBLIC_KEY is set in .env")
        print("2. LANGFUSE_SECRET_KEY is set in .env")
        print("3. Langfuse SDK is installed: pip install langfuse")
        return
    
    # Test trace creation
    trace = test_trace_creation(client)
    print()
    
    # Test generation logging
    if trace:
        test_generation_logging(trace)
        print()
    
    # Test flush
    test_flush(client)
    print()
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if client and trace:
        print("✓ Langfuse is configured and working")
        print("✓ Check your Langfuse dashboard for the test trace")
        print("  Look for trace name: 'test-trace'")
    else:
        print("✗ Langfuse is not working properly")
    print()

if __name__ == "__main__":
    main()

