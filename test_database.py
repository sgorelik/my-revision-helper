#!/usr/bin/env python3
"""
Test database connection and table creation.

Run this script to verify your database setup is working correctly.
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

def test_database_connection():
    """Test database connection."""
    print("Testing database connection...")
    try:
        from my_revision_helper.database import DATABASE_URL, engine, init_db
        
        if not DATABASE_URL:
            print("⚠ DATABASE_URL not set")
            print("   Set DATABASE_URL in .env file to enable database persistence")
            print("   Example: DATABASE_URL=postgresql://user:pass@localhost:5432/dbname")
            return False
        
        print(f"✓ DATABASE_URL is set")
        
        if not engine:
            print("✗ Database engine not available")
            return False
        
        print("✓ Database engine created")
        
        # Test connection
        with engine.connect() as conn:
            print("✓ Database connection successful")
        
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def test_table_creation():
    """Test table creation."""
    print("\nTesting table creation...")
    try:
        from my_revision_helper.database import init_db, engine
        from my_revision_helper.models_db import User, Revision, RevisionRun, RunQuestion, RunAnswer
        
        if not engine:
            print("⚠ Database engine not available - skipping table creation test")
            return False
        
        # Initialize database (creates tables)
        init_db()
        print("✓ Database initialization completed")
        
        # Verify tables exist by checking if we can query them
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = ['users', 'revisions', 'revision_runs', 'run_questions', 'run_answers']
        missing_tables = [t for t in expected_tables if t not in tables]
        
        if missing_tables:
            print(f"✗ Missing tables: {missing_tables}")
            return False
        
        print(f"✓ All tables created: {', '.join(expected_tables)}")
        return True
    except Exception as e:
        print(f"✗ Table creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_storage_adapter():
    """Test storage adapter with database."""
    print("\nTesting storage adapter...")
    try:
        from my_revision_helper.database import get_db, engine
        from my_revision_helper.storage import StorageAdapter
        
        if not engine:
            print("⚠ Database engine not available - skipping storage adapter test")
            return False
        
        # Get a database session
        db_gen = get_db()
        db = next(db_gen)
        
        if not db:
            print("⚠ Database session not available")
            return False
        
        # Test storage adapter
        storage = StorageAdapter(user=None, db=db, session_id="test-session-123")
        print(f"✓ Storage adapter created")
        print(f"  - Uses database: {storage.use_database}")
        print(f"  - Is authenticated: {storage.is_authenticated}")
        print(f"  - Session ID: {storage.session_id}")
        
        db_gen.close()
        return True
    except Exception as e:
        print(f"✗ Storage adapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Database Setup Test")
    print("=" * 60)
    print()
    
    results = []
    results.append(("Database Connection", test_database_connection()))
    results.append(("Table Creation", test_table_creation()))
    results.append(("Storage Adapter", test_storage_adapter()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL / ⚠ SKIP"
        print(f"{name:25} {status}")
    
    all_passed = all(r for _, r in results)
    print("=" * 60)
    if all_passed:
        print("✓ All tests passed! Database is ready to use.")
        sys.exit(0)
    else:
        print("⚠ Some tests failed or were skipped")
        print("   Set DATABASE_URL in .env to enable full database functionality")
        sys.exit(1)

