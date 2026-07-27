#!/usr/bin/env python3
"""
Database migration: Add the study programme schema.

Creates the tables behind children, their subjects and weekly plans, the paper
library, assignments, submissions, marking and topic mastery. Also links the
existing revision tables to a child so practice runs can be attributed, and to
a marking so retests know where they came from.

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


# Tables created from the SQLAlchemy models, in dependency order.
NEW_TABLES = [
    "children",
    "child_subjects",
    "study_plans",
    "plan_blocks",
    "stored_files",
    "papers",
    "paper_questions",
    "assignments",
    "submissions",
    "markings",
    "question_marks",
    "topic_mastery",
    "score_log",
]

# Additive columns on pre-existing tables.
NEW_COLUMNS = [
    ("revisions", "child_id", "child_id VARCHAR"),
    ("revisions", "source_marking_id", "source_marking_id VARCHAR"),
    ("revision_runs", "child_id", "child_id VARCHAR"),
]

# Indexes that matter for the dashboard queries.
INDEXES = [
    ("idx_assignments_child_status", "assignments", "(child_id, status)"),
    ("idx_paper_questions_paper", "paper_questions", "(paper_id, order_index)"),
    ("idx_question_marks_marking", "question_marks", "(marking_id, order_index)"),
    ("idx_topic_mastery_child", "topic_mastery", "(child_id, subject)"),
    ("idx_score_log_child", "score_log", "(child_id, subject)"),
    ("idx_children_user", "children", "(user_id)"),
]


def create_tables(engine):
    """Create any missing tables from the ORM metadata."""
    from my_revision_helper.database import Base
    from my_revision_helper import models_db  # noqa: F401  (registers the models)

    inspector = inspect(engine)
    missing = [t for t in NEW_TABLES if not inspector.has_table(t)]

    if not missing:
        print("All study programme tables already exist. Skipping table creation.")
        return

    print(f"\nCreating {len(missing)} table(s): {', '.join(missing)}")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created")


def add_columns(engine):
    """Add the additive columns linking revisions to children and markings."""
    inspector = inspect(engine)

    for table_name, column_name, column_def in NEW_COLUMNS:
        if not inspector.has_table(table_name):
            print(f"Table {table_name} does not exist yet. Skipping {column_name}.")
            continue

        existing = {c["name"] for c in inspector.get_columns(table_name)}
        if column_name in existing:
            print(f"Column {table_name}.{column_name} already exists. Skipping.")
            continue

        print(f"\nAdding {table_name}.{column_name}...")
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
        print(f"✓ Added {table_name}.{column_name}")
        inspector = inspect(engine)


def add_foreign_keys(engine):
    """
    Link revisions/revision_runs to children.

    Kept separate from the column creation so that a failure here (for example
    on a database where the constraint already exists under a different name)
    cannot roll back the column itself.
    """
    inspector = inspect(engine)
    if not inspector.has_table("children"):
        return

    constraints = [
        ("fk_revisions_child", "revisions", "child_id", "children(id)"),
        ("fk_revision_runs_child", "revision_runs", "child_id", "children(id)"),
    ]

    for name, table, column, target in constraints:
        if not inspector.has_table(table):
            continue
        existing = {fk.get("name") for fk in inspector.get_foreign_keys(table)}
        if name in existing:
            print(f"Foreign key {name} already exists. Skipping.")
            continue
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                        f"FOREIGN KEY ({column}) REFERENCES {target}"
                    )
                )
            print(f"✓ Added foreign key {name}")
        except Exception as e:
            print(f"⚠️  Could not add foreign key {name} (continuing): {e}")


def add_indexes(engine):
    """Create the dashboard query indexes if they are missing."""
    inspector = inspect(engine)

    for index_name, table_name, columns in INDEXES:
        if not inspector.has_table(table_name):
            continue
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {columns}")
                )
        except Exception as e:
            print(f"⚠️  Could not create index {index_name} (continuing): {e}")

    print("✓ Indexes ensured")


def run_migration():
    print("=" * 70)
    print("Database Migration: Study Programme (children, papers, assignments)")
    print("=" * 70)

    engine = create_engine(DATABASE_URL)

    create_tables(engine)
    add_columns(engine)
    add_foreign_keys(engine)
    add_indexes(engine)

    print("\n" + "=" * 70)
    print("Migration completed successfully!")
    print("=" * 70)
    print("\nThe database now supports:")
    print("  - children + child_subjects: per-kid profiles and subject baselines")
    print("  - study_plans + plan_blocks: the weekly timetable")
    print("  - stored_files + papers + paper_questions: the paper library")
    print("  - assignments + submissions: work given out and handed in")
    print("  - markings + question_marks: per-question scores and feedback")
    print("  - topic_mastery + score_log: progress tracking over time")


if __name__ == "__main__":
    try:
        # Make the package importable when run as a standalone script.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
