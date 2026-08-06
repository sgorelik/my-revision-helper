#!/usr/bin/env python3
"""
Put existing chart points on the day the work was done.

Score log entries were stamped with the moment the mark was written, which is
the same thing as the day of the work only when a paper is marked the day it is
handed in. Catching up a fortnight of paper worksheets in one evening stacked
that whole fortnight onto the evening, flattening the trend line into a single
column just when a family most wants to see progress over a summer.

Only entries backed by a piece of work with a completion date are moved, and
each is moved at most once, so this is safe to run repeatedly.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

REQUIRED_TABLES = ("score_log", "markings", "submissions", "assignments")

# Postgres and SQLite disagree about date arithmetic, so compare the calendar
# day only and let each database cast in its own way.
REDATE = text(
    """
    UPDATE score_log
    SET recorded_at = source.completed_at
    FROM (
        SELECT s.id AS score_id, a.completed_at AS completed_at
        FROM score_log s
        JOIN markings m ON m.id = s.marking_id
        JOIN submissions sub ON sub.id = m.submission_id
        JOIN assignments a ON a.id = sub.assignment_id
        WHERE a.completed_at IS NOT NULL
    ) AS source
    WHERE score_log.id = source.score_id
      AND CAST(score_log.recorded_at AS DATE) <> CAST(source.completed_at AS DATE)
    """
)


def run_migration() -> None:
    if not DATABASE_URL:
        print("⚠️  DATABASE_URL not set - skipping")
        return

    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)

    missing = [name for name in REQUIRED_TABLES if not inspector.has_table(name)]
    if missing:
        print(f"Tables not created yet ({', '.join(missing)}). Skipping.")
        return

    with engine.begin() as conn:
        result = conn.execute(REDATE)

    moved = result.rowcount or 0
    if moved:
        print(f"✓ Moved {moved} chart point(s) onto the day the work was done")
    else:
        print("✓ Every chart point already sits on the day of its work")


if __name__ == "__main__":
    try:
        run_migration()
        print("\n✅ Migration complete")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
