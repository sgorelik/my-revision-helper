"""
Database configuration and session management.

This module sets up SQLAlchemy for database connections.
Supports PostgreSQL (production) and can work without database (fallback to in-memory).
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Optional, Generator
import os
import logging

# Load environment variables from .env file (must be before reading DATABASE_URL)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment (Railway provides this automatically)
DATABASE_URL = os.getenv("DATABASE_URL")

# Only create engine if DATABASE_URL is set
if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("Database connection configured")
    except Exception as e:
        logger.warning(f"Failed to configure database: {e}")
        engine = None
        SessionLocal = None
else:
    logger.info("DATABASE_URL not set - database features disabled")
    engine = None
    SessionLocal = None

Base = declarative_base()

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
    if engine:
        from .models_db import User, Revision, RevisionRun, RunQuestion, RunAnswer
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")
    else:
        logger.info("Database not configured - skipping table creation")

