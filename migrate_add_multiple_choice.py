#!/usr/bin/env python3
"""
Database migration script to add multiple choice question support.

This script adds the following columns to the database:
- revisions.question_style (String, default='free-text')
- run_questions.question_style (String)
- run_questions.options (JSON)
- run_questions.correct_answer_index (Integer)
- run_questions.rationale (Text)

Run this script once to update your database schema.

Usage:
    python migrate_add_multiple_choice.py
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text, inspect, create_engine
from my_revision_helper.database import get_db, engine, DATABASE_URL

def migrate():
    """Add multiple choice columns to database tables."""
    print("=" * 70)
    print("Database Migration: Adding Multiple Choice Support")
    print("=" * 70)
    print()
    
    # Ensure we have a database connection
    if not DATABASE_URL:
        print("❌ DATABASE_URL not set. Cannot run migration.")
        raise Exception("DATABASE_URL not set")
    
    # Use the engine from database module, or create a new one if needed
    migration_engine = engine
    if not migration_engine:
        print("Creating database engine for migration...")
        migration_engine = create_engine(DATABASE_URL)
    
    db = next(get_db())
    
    try:
        # Check if columns already exist
        inspector = inspect(migration_engine)
        
        # Check if tables exist first
        if not inspector.has_table('revisions'):
            print("⚠️  revisions table does not exist. Skipping question_style migration for revisions.")
            revision_columns = []
        else:
            revision_columns = [col['name'] for col in inspector.get_columns('revisions')]
        
        if not inspector.has_table('run_questions'):
            print("⚠️  run_questions table does not exist. Skipping multiple choice migration for run_questions.")
            question_columns = []
        else:
            question_columns = [col['name'] for col in inspector.get_columns('run_questions')]
        
        # Add question_style to revisions table
        if 'question_style' not in revision_columns:
            print("Adding question_style column to revisions table...")
            try:
                db.execute(text("ALTER TABLE revisions ADD COLUMN question_style VARCHAR DEFAULT 'free-text'"))
                db.commit()
                print("✓ Added question_style to revisions")
            except Exception as e:
                db.rollback()
                print(f"⚠️  Error adding question_style to revisions: {e}")
                print("   This might be OK if the column already exists")
                # Check again after error
                revision_columns = [col['name'] for col in inspector.get_columns('revisions')]
                if 'question_style' in revision_columns:
                    print("   Column exists now - continuing")
                else:
                    raise
        else:
            print("ℹ question_style column already exists in revisions table")
        
        # Add multiple choice columns to run_questions table
        if 'question_style' not in question_columns:
            print("Adding question_style column to run_questions table...")
            db.execute(text("ALTER TABLE run_questions ADD COLUMN question_style VARCHAR"))
            db.commit()
            print("✓ Added question_style to run_questions")
        else:
            print("ℹ question_style column already exists in run_questions table")
        
        if 'options' not in question_columns:
            print("Adding options column to run_questions table...")
            db.execute(text("ALTER TABLE run_questions ADD COLUMN options JSON"))
            db.commit()
            print("✓ Added options to run_questions")
        else:
            print("ℹ options column already exists in run_questions table")
        
        if 'correct_answer_index' not in question_columns:
            print("Adding correct_answer_index column to run_questions table...")
            db.execute(text("ALTER TABLE run_questions ADD COLUMN correct_answer_index INTEGER"))
            db.commit()
            print("✓ Added correct_answer_index to run_questions")
        else:
            print("ℹ correct_answer_index column already exists in run_questions table")
        
        if 'rationale' not in question_columns:
            print("Adding rationale column to run_questions table...")
            db.execute(text("ALTER TABLE run_questions ADD COLUMN rationale TEXT"))
            db.commit()
            print("✓ Added rationale to run_questions")
        else:
            print("ℹ rationale column already exists in run_questions table")
        
        print()
        print("=" * 70)
        print("Migration completed successfully!")
        print("=" * 70)
        print()
        print("You can now use multiple choice questions in your revisions.")
        print("Existing questions will continue to work (they'll be treated as free-text).")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        print("\nIf you're using SQLite, you may need to recreate the database.")
        print("Or manually add the columns using your database client.")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

