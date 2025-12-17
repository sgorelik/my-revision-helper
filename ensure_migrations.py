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
        return True  # Column exists
    
    print(f"⚠️  Column {table_name}.{column_name} is missing - adding it...")
    
    try:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
            conn.commit()
        print(f"✅ Added {table_name}.{column_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to add {table_name}.{column_name}: {e}")
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
    else:
        print("⚠️  Some columns may be missing - check errors above")
    print("="*70)
    
    sys.exit(0 if all_good else 1)

if __name__ == "__main__":
    main()

