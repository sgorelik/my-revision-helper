#!/usr/bin/env python3
"""
Database migration: the day a piece of work is planned for.

Adds `scheduled_date` to assignments. This is distinct from `due_date`: a study
plan says "do the Maths workbook on Monday" while the deadline might be Friday,
and a day view needs the former.

Existing rows keep a null scheduled date and fall back to their due date, so
nothing has to be backfilled.

Idempotent: safe to run repeatedly.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.inspection import inspect

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)


NEW_COLUMNS = [
    ("assignments", "scheduled_date", "scheduled_date TIMESTAMP"),
]

# Days are looked up constantly by the day and week views.
NEW_INDEXES = [
    (
        "idx_assignments_child_scheduled",
        "CREATE INDEX IF NOT EXISTS idx_assignments_child_scheduled "
        "ON assignments (child_id, scheduled_date)",
    ),
]


def run_migration() -> None:
    print("=" * 70)
    print("Database Migration: scheduled_date on assignments")
    print("=" * 70)

    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)

    for table_name, column_name, column_def in NEW_COLUMNS:
        if not inspector.has_table(table_name):
            print(f"Table {table_name} does not exist yet. Skipping {column_name}.")
            continue

        existing = {c["name"] for c in inspector.get_columns(table_name)}
        if column_name in existing:
            print(f"Column {table_name}.{column_name} already exists. Skipping.")
            continue

        print(f"Adding {table_name}.{column_name}...")
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
        print(f"✓ Added {table_name}.{column_name}")

    inspector = inspect(engine)
    if inspector.has_table("assignments"):
        for name, statement in NEW_INDEXES:
            print(f"Ensuring index {name}...")
            with engine.begin() as conn:
                conn.execute(text(statement))
            print(f"✓ {name}")

    print("\n" + "=" * 70)
    print("Migration completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
