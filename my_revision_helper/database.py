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
            logger.info("✅ Database tables initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create database tables: {e}", exc_info=True)
            raise
    else:
        logger.warning("⚠️ Database not configured - skipping table creation (engine is None)")

