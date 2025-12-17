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
    question_style = Column(String, default="free-text")  # 'free-text' or 'multiple-choice'
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
    question_style = Column(String)  # 'free-text' or 'multiple-choice'
    options = Column(JSON)  # List of strings for multiple choice questions
    correct_answer_index = Column(Integer)  # 0-based index for multiple choice questions
    rationale = Column(Text)  # Prefetched explanation for multiple choice questions
    
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


class QuestionFlag(Base):
    """User flags for questions - feedback on question quality."""
    __tablename__ = "question_flags"
    
    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("revision_runs.id"), nullable=False)
    question_id = Column(String, ForeignKey("run_questions.id"), nullable=False)
    flag_type = Column(String, nullable=False)  # 'incorrect', 'not on topic', "haven't studied material", 'poorly formulated'
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Nullable for anonymous users
    session_id = Column(String, nullable=True)  # For anonymous users
    langfuse_trace_id = Column(String, nullable=True)  # Associated Langfuse trace ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    run = relationship("RevisionRun")
    question = relationship("RunQuestion")


class PrepCheck(Base):
    """Prep check submissions and AI feedback."""
    __tablename__ = "prep_checks"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Nullable for anonymous users
    session_id = Column(String, nullable=True)  # For anonymous users
    previous_prep_check_id = Column(String, ForeignKey("prep_checks.id"), nullable=True)  # Link to previous version
    subject = Column(String, nullable=False)
    description = Column(Text)  # Optional additional criteria
    prep_work_text = Column(Text, nullable=False)  # Combined text from files and description
    uploaded_files = Column(JSON)  # List of filenames
    feedback = Column(Text, nullable=False)  # AI-generated feedback
    langfuse_trace_id = Column(String, nullable=True)  # Associated Langfuse trace ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    previous_prep_check = relationship("PrepCheck", remote_side=[id], backref="updated_versions")

