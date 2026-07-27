#!/usr/bin/env python3
"""
Database migration: prerequisite resource links.

Adds a JSON `resources` column to papers and assignments. A paper's links are
the ones intrinsic to the material — the video to watch before attempting it —
and travel with it every time it is assigned. An assignment's are one-off
additions for that setting.

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


# JSON rather than JSONB: the existing tables use JSON throughout and nothing
# queries inside these values.
NEW_COLUMNS = [
    ("papers", "resources", "resources JSON"),
    ("assignments", "resources", "resources JSON"),
]


def add_columns(engine) -> None:
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


def run_migration() -> None:
    print("=" * 70)
    print("Database Migration: Resource links on papers and assignments")
    print("=" * 70)

    engine = create_engine(DATABASE_URL)
    add_columns(engine)

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
