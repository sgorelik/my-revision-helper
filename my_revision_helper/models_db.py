"""
Database models for persistent storage.

These models represent the database schema for users, revisions, runs, questions, and answers.
Supports both authenticated users (with user_id) and anonymous sessions (with session_id).
"""

from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    """Authenticated users from Auth0."""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)  # Auth0 user_id (sub claim)
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    picture = Column(String)  # Profile picture URL
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    revisions = relationship("Revision", back_populates="user", cascade="all, delete-orphan", foreign_keys="Revision.user_id")
    runs = relationship("RevisionRun", back_populates="user", cascade="all, delete-orphan", foreign_keys="RevisionRun.user_id")


class Revision(Base):
    """Revision definitions - can belong to authenticated user or anonymous session."""
    __tablename__ = "revisions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Nullable for anonymous users
    session_id = Column(String, nullable=True)  # For anonymous users - not retrievable later
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    topics = Column(JSON)  # List of strings
    description = Column(Text)
    desired_question_count = Column(Integer, nullable=False)
    accuracy_threshold = Column(Integer, nullable=False)
    extracted_texts = Column(JSON)  # Dict of filename -> text
    uploaded_files = Column(JSON)  # List of filenames
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="revisions", foreign_keys=[user_id])
    runs = relationship("RevisionRun", back_populates="revision", cascade="all, delete-orphan")


class RevisionRun(Base):
    """Revision run/session - tracks progress through questions."""
    __tablename__ = "revision_runs"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Nullable for anonymous users
    session_id = Column(String, nullable=True)  # For anonymous users
    revision_id = Column(String, ForeignKey("revisions.id"), nullable=False)
    status = Column(String, default="running")  # running, completed
    current_question_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="runs", foreign_keys=[user_id])
    revision = relationship("Revision", back_populates="runs")
    questions = relationship("RunQuestion", back_populates="run", cascade="all, delete-orphan")
    answers = relationship("RunAnswer", back_populates="run", cascade="all, delete-orphan")


class RunQuestion(Base):
    """Questions generated for a specific run."""
    __tablename__ = "run_questions"
    
    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("revision_runs.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_index = Column(Integer, nullable=False)  # Order in the run
    
    run = relationship("RevisionRun", back_populates="questions")


class RunAnswer(Base):
    """Student answers and marking results."""
    __tablename__ = "run_answers"
    
    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("revision_runs.id"), nullable=False)
    question_id = Column(String, ForeignKey("run_questions.id"), nullable=False)
    student_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    score = Column(String)  # "Full Marks", "Partial Marks", "Incorrect"
    correct_answer = Column(Text)
    explanation = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    run = relationship("RevisionRun", back_populates="answers")
    question = relationship("RunQuestion")

