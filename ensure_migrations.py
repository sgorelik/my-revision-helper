#!/usr/bin/env python3
"""
Ensure database migrations have run - add missing columns if needed.

This script checks for critical missing columns and adds them if they don't exist.
It's a safety net in case migrations didn't run properly.
"""

import os
import sys
from sqlalchemy import text, inspect, create_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("⚠️  DATABASE_URL not set - skipping column checks")
    sys.exit(0)

def ensure_column_exists(engine, table_name: str, column_name: str, column_def: str):
    """Check if a column exists, add it if missing."""
    inspector = inspect(engine)
    
    if not inspector.has_table(table_name):
        print(f"⚠️  Table {table_name} does not exist - skipping column check")
        return False
    
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    
    if column_name in columns:
        print(f"✅ Column {table_name}.{column_name} already exists")
        return True  # Column exists
    
    print(f"⚠️  Column {table_name}.{column_name} is missing - adding it...")
    
    try:
        with engine.begin() as conn:  # Use begin() for automatic transaction management
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
        
        # Verify it was added
        inspector = inspect(engine)
        columns_after = [col['name'] for col in inspector.get_columns(table_name)]
        if column_name in columns_after:
            print(f"✅ Successfully added {table_name}.{column_name}")
            return True
        else:
            print(f"❌ Column {table_name}.{column_name} was not added (verification failed)")
            return False
    except Exception as e:
        # Check if column was added by another process
        inspector = inspect(engine)
        columns_after = [col['name'] for col in inspector.get_columns(table_name)]
        if column_name in columns_after:
            print(f"✅ Column {table_name}.{column_name} exists now (may have been added concurrently)")
            return True
        print(f"❌ Failed to add {table_name}.{column_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Check and add missing critical columns."""
    print("="*70)
    print("Ensuring Database Schema is Up to Date")
    print("="*70)
    
    engine = create_engine(DATABASE_URL)
    
    # Critical columns that must exist
    critical_columns = [
        ("revisions", "question_style", "question_style VARCHAR DEFAULT 'free-text'"),
        ("run_questions", "question_style", "question_style VARCHAR"),
        ("run_questions", "options", "options JSON"),
        ("run_questions", "correct_answer_index", "correct_answer_index INTEGER"),
        ("run_questions", "rationale", "rationale TEXT"),
    ]
    
    all_good = True
    for table, column, definition in critical_columns:
        if not ensure_column_exists(engine, table, column, definition):
            all_good = False
    
    print("\n" + "="*70)
    if all_good:
        print("✅ All critical columns exist")
        print("="*70)
        sys.exit(0)
    else:
        print("❌ CRITICAL: Some columns are missing!")
        print("   The server may fail to start or operate correctly.")
        print("   Check errors above for details.")
        print("="*70)
        print("\n⚠️  Exiting with error code to prevent server startup with broken schema")
        sys.exit(1)

if __name__ == "__main__":
    main()

