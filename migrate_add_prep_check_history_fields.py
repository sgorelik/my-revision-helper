#!/usr/bin/env python3
"""
Database migration: add prep check history fields.

Adds:
- prep_checks.approx_score (INTEGER, nullable)
- prep_checks.assessed_at (TIMESTAMP, nullable)

Backfills:
- assessed_at = created_at where assessed_at is null
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("⚠️  DATABASE_URL not set - skipping migration")
    sys.exit(0)


def ensure_column(engine, table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table):
        print(f"⚠️  Table {table} does not exist - skipping")
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        print(f"✅ Column {table}.{column} already exists")
        return
    print(f"Adding column {table}.{column} ...")
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    print(f"✓ Added {table}.{column}")


def main():
    print("=" * 70)
    print("Database Migration: Add Prep Check History Fields")
    print("=" * 70)

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    ensure_column(engine, "prep_checks", "approx_score", "approx_score INTEGER")
    ensure_column(engine, "prep_checks", "assessed_at", "assessed_at TIMESTAMP")

    # Backfill assessed_at from created_at if missing
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE prep_checks SET assessed_at = created_at "
                    "WHERE assessed_at IS NULL"
                )
            )
        print("✓ Backfilled assessed_at from created_at where missing")
    except Exception as e:
        print(f"⚠️  Could not backfill assessed_at (continuing): {e}")

    print("=" * 70)
    print("✅ Migration completed")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


