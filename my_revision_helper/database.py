"""
Database configuration and session management.

This module sets up SQLAlchemy for database connections.
Supports PostgreSQL (production) and can work without database (fallback to in-memory).
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Optional, Generator
import os
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file (must be before reading DATABASE_URL)
try:
    from dotenv import load_dotenv
    try:
        load_dotenv()
    except (OSError, PermissionError) as e:
        # In some environments (e.g., restricted sandboxes), reading .env may be disallowed.
        # Fail soft: environment variables may still be provided via the process environment.
        logger.warning(f"⚠️ Could not load .env file (continuing): {e}")
except ImportError:
    pass  # dotenv is optional

# Get DATABASE_URL from environment (Railway provides this automatically)
DATABASE_URL = os.getenv("DATABASE_URL")

# Only create engine if DATABASE_URL is set
if DATABASE_URL:
    try:
        logger.info(f"Creating database engine with DATABASE_URL: {DATABASE_URL[:50]}...")  # Log first 50 chars for security
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("✅ Database connection configured successfully")
    except Exception as e:
        logger.error(f"❌ Failed to configure database: {e}", exc_info=True)
        engine = None
        SessionLocal = None
else:
    logger.warning("⚠️ DATABASE_URL not set - database features disabled")
    engine = None
    SessionLocal = None

Base = declarative_base()

def _ensure_critical_columns(engine) -> None:
    """
    Best-effort safety net: ensure certain additive columns exist.

    SQLAlchemy's create_all() does not alter existing tables, so local DBs (and
    any environment where migrations were skipped) can end up missing columns
    required by newer code.

    This function is intentionally additive-only and idempotent.
    """
    inspector = inspect(engine)

    critical_columns: list[tuple[str, str, str]] = [
        # Multiple choice support
        ("revisions", "question_style", "question_style VARCHAR DEFAULT 'free-text'"),
        ("run_questions", "question_style", "question_style VARCHAR"),
        ("run_questions", "options", "options JSON"),
        ("run_questions", "correct_answer_index", "correct_answer_index INTEGER"),
        ("run_questions", "rationale", "rationale TEXT"),
        # Prep check history fields
        ("prep_checks", "approx_score", "approx_score INTEGER"),
        ("prep_checks", "assessed_at", "assessed_at TIMESTAMP"),
        # Study programme: attribute revisions and runs to a child
        ("revisions", "child_id", "child_id VARCHAR"),
        ("revisions", "source_marking_id", "source_marking_id VARCHAR"),
        ("revision_runs", "child_id", "child_id VARCHAR"),
    ]

    for table_name, column_name, column_def in critical_columns:
        if not inspector.has_table(table_name):
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        if column_name in existing_cols:
            continue
        logger.warning(f"⚠️ Missing column detected: {table_name}.{column_name} — adding it")
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
        # Refresh inspector cache for subsequent checks
        inspector = inspect(engine)

def get_db() -> Generator[Optional[sessionmaker], None, None]:
    """
    Get database session - returns None if database not configured.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(db: Session = Depends(get_db)):
            if db:
                # Use database
            else:
                # Fallback to in-memory
    """
    if not SessionLocal:
        yield None
        return
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all database tables if database is configured."""
    logger.info(f"init_db() called - DATABASE_URL is {'SET' if DATABASE_URL else 'NOT SET'}")
    logger.info(f"init_db() called - engine is {'SET' if engine else 'NOT SET'}")
    
    if engine:
        try:
            from .models_db import User, Revision, RevisionRun, RunQuestion, RunAnswer
            logger.info("Importing models for table creation...")
            Base.metadata.create_all(bind=engine)
            # Safety net for additive schema changes when migrations weren't run.
            _ensure_critical_columns(engine)
            logger.info("✅ Database tables initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create database tables: {e}", exc_info=True)
            raise
    else:
        logger.warning("⚠️ Database not configured - skipping table creation (engine is None)")

