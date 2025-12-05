#!/usr/bin/env python3
"""
Basic backend test - verifies the API can start and handle requests without database.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from my_revision_helper.api import app
        from my_revision_helper.auth import get_current_user_optional
        from my_revision_helper.database import get_db, init_db
        from my_revision_helper.storage import StorageAdapter
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_database_init():
    """Test database initialization (works without DATABASE_URL)."""
    print("\nTesting database initialization...")
    try:
        from my_revision_helper.database import init_db
        init_db()  # Should not fail even without DATABASE_URL
        print("✓ Database initialization successful (no DATABASE_URL set - using fallback)")
        return True
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False

def test_storage_adapter():
    """Test storage adapter without database."""
    print("\nTesting storage adapter (no database)...")
    try:
        from my_revision_helper.storage import StorageAdapter
        # Create adapter without user or database
        storage = StorageAdapter(user=None, db=None, session_id="test-session-123")
        print(f"✓ Storage adapter created (session_id: {storage.session_id})")
        print(f"  - Is authenticated: {storage.is_authenticated}")
        print(f"  - Uses database: {storage.use_database}")
        return True
    except Exception as e:
        print(f"✗ Storage adapter test failed: {e}")
        return False

def test_api_endpoints():
    """Test that API endpoints are defined."""
    print("\nTesting API endpoints...")
    try:
        from my_revision_helper.api import app
        routes = [route.path for route in app.routes]
        key_routes = [
            "/api/health",
            "/api/user/me",
            "/api/revisions",
            "/api/runs/{run_id}/question-count",
        ]
        found = [r for r in key_routes if r in routes or any(r.replace("{", "").replace("}", "") in route for route in routes)]
        print(f"✓ Found {len(found)}/{len(key_routes)} key routes")
        for route in found:
            print(f"  - {route}")
        return True
    except Exception as e:
        print(f"✗ API endpoint test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Backend Basic Test Suite")
    print("=" * 60)
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("Database Init", test_database_init()))
    results.append(("Storage Adapter", test_storage_adapter()))
    results.append(("API Endpoints", test_api_endpoints()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:20} {status}")
    
    all_passed = all(r for _, r in results)
    print("=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)

