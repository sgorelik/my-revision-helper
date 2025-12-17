#!/usr/bin/env python3
"""
Database migration: Add previous_prep_check_id column to prep_checks table for versioning.

This migration adds a foreign key column to link updated prep checks to their previous versions.
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.inspection import inspect

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_previous_prep_check_id_column(engine):
    """Add previous_prep_check_id column to prep_checks table if it doesn't exist."""
    if not column_exists(engine, "prep_checks", "previous_prep_check_id"):
        print("\nAdding previous_prep_check_id column to prep_checks table...")
        
        with engine.connect() as conn:
            # Add the column
            conn.execute(text("""
                ALTER TABLE prep_checks 
                ADD COLUMN previous_prep_check_id VARCHAR
            """))
            
            # Add foreign key constraint
            conn.execute(text("""
                ALTER TABLE prep_checks 
                ADD CONSTRAINT fk_prep_checks_previous 
                FOREIGN KEY (previous_prep_check_id) 
                REFERENCES prep_checks(id)
            """))
            
            conn.commit()
        
        print("✓ Added previous_prep_check_id column with foreign key constraint")
    else:
        print("Column previous_prep_check_id already exists. Skipping.")


def run_migration():
    print("=" * 70)
    print("Database Migration: Adding Versioning to Prep Checks")
    print("=" * 70)

    engine = create_engine(DATABASE_URL)

    # Check if prep_checks table exists
    inspector = inspect(engine)
    if not inspector.has_table("prep_checks"):
        print("\nERROR: prep_checks table does not exist.")
        print("Please run migrate_add_prep_checks.py first to create the table.")
        sys.exit(1)

    # Add previous_prep_check_id column
    add_previous_prep_check_id_column(engine)

    print("\n" + "=" * 70)
    print("Migration completed successfully!")
    print("=" * 70)
    print("\nThe prep_checks table now supports versioning:")
    print("  - previous_prep_check_id: Foreign key to link updated prep checks")
    print("  - Users can now upload updated versions of their prep work")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


