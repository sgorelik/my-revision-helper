#!/usr/bin/env python3
"""
Database migration: timing a sitting.

Adds the stopwatch columns to assignments, plus how long the work took and how
many pauses were taken to submissions, so a child can press start and finish
instead of estimating minutes afterwards.

The clock lives in the database rather than the browser: a child will reload the
page or move device mid-paper, and the elapsed time has to survive that.

Existing rows default to an idle timer and zero pauses, and existing submissions
keep their self-reported minutes with `timed` false, so nothing needs
backfilling.

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
    ("assignments", "timer_state", "timer_state VARCHAR DEFAULT 'idle'"),
    ("assignments", "timer_started_at", "timer_started_at TIMESTAMP"),
    ("assignments", "timer_accumulated_seconds", "timer_accumulated_seconds INTEGER DEFAULT 0"),
    ("assignments", "timer_pause_count", "timer_pause_count INTEGER DEFAULT 0"),
    ("assignments", "timer_first_started_at", "timer_first_started_at TIMESTAMP"),
    ("assignments", "timer_stopped_at", "timer_stopped_at TIMESTAMP"),
    ("submissions", "timed", "timed BOOLEAN DEFAULT FALSE"),
    ("submissions", "pause_count", "pause_count INTEGER DEFAULT 0"),
]


def run_migration() -> None:
    print("=" * 70)
    print("Database Migration: assignment timer")
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
