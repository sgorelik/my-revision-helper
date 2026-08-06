#!/usr/bin/env python3
"""
Let a single piece of marked work be taken back or put right.

Adds:
  - deleted_at on assignments, submissions, markings and score_log, so one
    wrong entry can come off the chart without deleting the child.
  - status and review_reason on markings, so work that could not be read waits
    for a person instead of being recorded as a zero.
  - content_hash on submissions, so a resend after a timeout finds the record
    it already made.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

NEW_COLUMNS = [
    ("assignments", "deleted_at", "deleted_at TIMESTAMP"),
    ("submissions", "deleted_at", "deleted_at TIMESTAMP"),
    ("submissions", "content_hash", "content_hash VARCHAR"),
    ("markings", "deleted_at", "deleted_at TIMESTAMP"),
    ("markings", "status", "status VARCHAR DEFAULT 'marked'"),
    ("markings", "review_reason", "review_reason TEXT"),
    ("score_log", "deleted_at", "deleted_at TIMESTAMP"),
]

NEW_INDEXES = [
    ("submissions", "ix_submissions_content_hash", "content_hash"),
]


def run_migration() -> None:
    if not DATABASE_URL:
        print("⚠️  DATABASE_URL not set - skipping")
        return

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
    for table_name, index_name, column_name in NEW_INDEXES:
        if not inspector.has_table(table_name):
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing:
            print(f"Index {index_name} already exists. Skipping.")
            continue
        print(f"Adding index {index_name}...")
        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})")
            )
        print(f"✓ Added {index_name}")

    # Rows written before this migration were all real marks.
    if inspector.has_table("markings"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE markings SET status = 'marked' WHERE status IS NULL"))
        print("✓ Existing markings marked as confirmed")


if __name__ == "__main__":
    try:
        run_migration()
        print("\n✅ Migration complete")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
