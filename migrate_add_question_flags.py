#!/usr/bin/env python3
"""
Database migration: Add question_flags table for user feedback on questions.

This migration adds a new table to store user flags/feedback on questions,
which can be associated with Langfuse traces for prompt improvement.
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.inspection import inspect
from sqlalchemy.sql import text

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_revision_helper.database import Base
from my_revision_helper.models_db import QuestionFlag


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return inspector.has_table(table_name)


def create_question_flags_table(engine):
    """Create the question_flags table if it doesn't exist."""
    if table_exists(engine, QuestionFlag.__tablename__):
        print(f"Table {QuestionFlag.__tablename__} already exists. Skipping creation.")
        return
    
    print(f"\nCreating {QuestionFlag.__tablename__} table...")
    
    # Create table using SQLAlchemy
    Base.metadata.create_all(engine, tables=[QuestionFlag.__table__])
    
    print(f"✓ Created {QuestionFlag.__tablename__} table")


def run_migration():
    print("=" * 70)
    print("Database Migration: Adding Question Flags Table")
    print("=" * 70)

    engine = create_engine(DATABASE_URL)

    # Create question_flags table
    create_question_flags_table(engine)

    print("\n" + "=" * 70)
    print("Migration completed successfully!")
    print("=" * 70)
    print("\nThe question_flags table has been created with the following columns:")
    print("  - id: Primary key (String)")
    print("  - run_id: Foreign key to revision_runs (String)")
    print("  - question_id: Foreign key to run_questions (String)")
    print("  - flag_type: Type of flag (String)")
    print("  - user_id: Optional foreign key to users (String, nullable)")
    print("  - session_id: Optional session ID for anonymous users (String, nullable)")
    print("  - langfuse_trace_id: Optional Langfuse trace ID (String, nullable)")
    print("  - created_at: Timestamp (DateTime)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

