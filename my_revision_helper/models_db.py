"""
Database models for persistent storage.

These models represent the database schema for users, revisions, runs, questions, and answers.
Supports both authenticated users (with user_id) and anonymous sessions (with session_id).
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    JSON,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    LargeBinary,
)
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
    children = relationship("Child", back_populates="user", cascade="all, delete-orphan", foreign_keys="Child.user_id")


class Revision(Base):
    """Revision definitions - can belong to authenticated user or anonymous session."""
    __tablename__ = "revisions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Nullable for anonymous users
    session_id = Column(String, nullable=True)  # For anonymous users - not retrievable later
    child_id = Column(String, ForeignKey("children.id"), nullable=True)  # Which child this is for
    source_marking_id = Column(String, nullable=True)  # Set when generated as a retest from a marking
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
    child_id = Column(String, ForeignKey("children.id"), nullable=True)  # Which child sat this run
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
    approx_score = Column(Integer, nullable=True)  # Approximate score (0-100)
    assessed_at = Column(DateTime, default=datetime.utcnow)  # When feedback/score were produced
    langfuse_trace_id = Column(String, nullable=True)  # Associated Langfuse trace ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    previous_prep_check = relationship("PrepCheck", remote_side=[id], backref="updated_versions")


# ---------------------------------------------------------------------------
# Study programme: children, their subjects, and their weekly plan
# ---------------------------------------------------------------------------


class Child(Base):
    """
    A student being tracked. Children belong to a parent account (or an
    anonymous session) — they are profiles, not separate logins.
    """

    __tablename__ = "children"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Parent account
    session_id = Column(String, nullable=True)  # For anonymous parents
    name = Column(String, nullable=False)
    year_group = Column(String)  # e.g. "Year 10", "5th Form"
    school = Column(String)
    colour = Column(String, default="orange")  # Accent colour for their dashboard
    avatar_emoji = Column(String)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="children")
    subjects = relationship("ChildSubject", back_populates="child", cascade="all, delete-orphan")
    plans = relationship("StudyPlan", back_populates="child", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="child", cascade="all, delete-orphan")


class ChildSubject(Base):
    """
    Per-child, per-subject configuration: where they are now, where the year
    group is, and how much time the plan gives the subject each week.
    """

    __tablename__ = "child_subjects"

    id = Column(String, primary_key=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    subject = Column(String, nullable=False)
    baseline_score = Column(Float)  # Their most recent exam %
    year_average = Column(Float)  # Year-group average % for the same exam
    target_score = Column(Float)  # What we are aiming at
    weekly_minutes = Column(Integer, default=0)  # Time allocated by the plan
    priority = Column(Integer, default=0)  # Higher = more important
    focus_topics = Column(JSON)  # List of named weak topics from the report
    report_notes = Column(Text)  # What the school report flagged
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    child = relationship("Child", back_populates="subjects")


class StudyPlan(Base):
    """A dated study programme for one child, e.g. 'Summer 2026'."""

    __tablename__ = "study_plans"

    id = Column(String, primary_key=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text)  # Human-readable overview shown on the dashboard
    source_text = Column(Text)  # Original plan document text, for AI context
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    weekly_minutes_target = Column(Integer, default=0)
    days_per_week = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    child = relationship("Child", back_populates="plans")
    blocks = relationship("PlanBlock", back_populates="plan", cascade="all, delete-orphan")


class PlanBlock(Base):
    """
    One recurring slot in the weekly timetable, e.g. 'Monday block 1, Maths,
    index laws, 50 min'. week_cycle supports plans that alternate subjects
    between week A and week B.
    """

    __tablename__ = "plan_blocks"

    id = Column(String, primary_key=True)
    plan_id = Column(String, ForeignKey("study_plans.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday
    block_index = Column(Integer, nullable=False)  # 1 or 2
    subject = Column(String, nullable=False)
    focus = Column(Text)  # What to actually do in the block
    planned_minutes = Column(Integer, default=50)
    week_cycle = Column(String)  # 'A', 'B', or NULL for every week

    plan = relationship("StudyPlan", back_populates="blocks")


# ---------------------------------------------------------------------------
# Paper library
# ---------------------------------------------------------------------------


class StoredFile(Base):
    """
    Binary storage for uploaded documents, kept in the database so the app
    needs no object-store infrastructure.
    """

    __tablename__ = "stored_files"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    filename = Column(String, nullable=False)
    content_type = Column(String)
    size_bytes = Column(Integer)
    sha256 = Column(String)
    content = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Paper(Base):
    """
    A piece of work in the library: a workbook, past paper, or reading task.

    Workbooks arrive with their answer key at the back. We split it out at
    upload time: question_text is safe to show the student, answer_key_text is
    never returned by student-facing endpoints.
    """

    __tablename__ = "papers"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    paper_type = Column(String, default="workbook")  # workbook, past_paper, reading, other
    topics = Column(JSON)  # List of strings
    week_label = Column(String)  # e.g. "Week 1"
    year_group = Column(String)
    # Prerequisite links belonging to the material itself, e.g. the Khan Academy
    # video to watch before attempting it. Held on the paper rather than the
    # assignment so they travel with it every time it is set.
    # [{"url": str, "label": str, "kind": str}]
    resources = Column(JSON)
    source_file_id = Column(String, ForeignKey("stored_files.id"), nullable=True)
    full_text = Column(Text)  # Everything extracted from the document
    question_text = Column(Text)  # Student-safe portion (answer key removed)
    answer_key_text = Column(Text)  # Hidden from students
    total_marks = Column(Integer)
    estimated_minutes = Column(Integer)
    parse_status = Column(String, default="pending")  # pending, parsed, failed, manual
    parse_error = Column(Text)
    parsed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    questions = relationship(
        "PaperQuestion",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperQuestion.order_index",
    )


class PaperQuestion(Base):
    """
    A single question parsed out of a paper, with its expected answer taken
    from the paper's own answer key.
    """

    __tablename__ = "paper_questions"

    id = Column(String, primary_key=True)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=False)
    session_label = Column(String)  # e.g. "Session 1 — Indices"
    band = Column(String)  # warm-up, standard, exam-style, stretch
    number = Column(String)  # As printed, e.g. "7" or "8(a)"
    order_index = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    marks = Column(Integer, default=1)
    topic = Column(String)
    expected_answer = Column(Text)  # From the answer key — never sent to students
    marking_notes = Column(Text)

    paper = relationship("Paper", back_populates="questions")


# ---------------------------------------------------------------------------
# Assignments, submissions and marking
# ---------------------------------------------------------------------------


class Assignment(Base):
    """
    A unit of work given to a child. Either a paper to complete and hand in,
    or a checkable task like 'read this book for two hours'.
    """

    __tablename__ = "assignments"

    id = Column(String, primary_key=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    assignment_type = Column(String, default="paper")  # paper, task
    subject = Column(String, nullable=False)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=True)
    instructions = Column(Text)
    resource_url = Column(String)  # Legacy single link; read as a fallback
    # One-off links for this setting only. The paper's own resources are shown
    # first; these are appended.
    resources = Column(JSON)
    estimated_minutes = Column(Integer)
    due_date = Column(DateTime)
    # The day this is planned for, which is not the same as the day it is due:
    # a plan says "do the Maths workbook on Monday" while the deadline may be
    # Friday. Naive midnight, treated as a calendar date.
    scheduled_date = Column(DateTime)
    week_label = Column(String)
    # How we know it is done: upload work, self-report, log time, or nothing
    verification = Column(String, default="upload")  # upload, self_report, timer, none
    status = Column(String, default="todo")  # todo, in_progress, submitted, marked, done
    sort_order = Column(Integer, default=0)

    # Timing a sitting, so nobody has to estimate minutes afterwards.
    #
    # The clock is kept here rather than in the browser because a child will
    # reload the page, lock the iPad, or move to a laptop mid-paper, and none of
    # that should lose or fudge the time. Elapsed time is therefore always
    # derived: accumulated_seconds covers finished stretches, and while running
    # the live stretch is measured from timer_started_at.
    timer_state = Column(String, default="idle")  # idle, running, paused, stopped
    timer_started_at = Column(DateTime)  # Start of the current running stretch (UTC)
    timer_accumulated_seconds = Column(Integer, default=0)
    timer_pause_count = Column(Integer, default=0)
    timer_first_started_at = Column(DateTime)  # When they first sat down
    timer_stopped_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    child = relationship("Child", back_populates="assignments")
    paper = relationship("Paper")
    submissions = relationship("Submission", back_populates="assignment", cascade="all, delete-orphan")


class Submission(Base):
    """A child handing in work (or reporting time spent) against an assignment."""

    __tablename__ = "submissions"

    id = Column(String, primary_key=True)
    assignment_id = Column(String, ForeignKey("assignments.id"), nullable=False)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    minutes_spent = Column(Integer)
    # Kept with the work rather than only on the assignment, so the record of
    # how long it took survives the assignment being timed again.
    timed = Column(Boolean, default=False)  # Measured rather than self-reported
    pause_count = Column(Integer, default=0)
    note = Column(Text)  # Child's own comment
    extracted_text = Column(Text)  # OCR/text of the handed-in work
    file_ids = Column(JSON)  # List of stored_files ids
    # One image per page of the work, kept because a transcript cannot hold a
    # graph the child drew. Shown back to them and used when marking a diagram.
    page_image_ids = Column(JSON)  # List of stored_files ids, in page order
    uploaded_files = Column(JSON)  # List of filenames, for display
    status = Column(String, default="submitted")  # submitted, marking, marked, failed
    submitted_at = Column(DateTime, default=datetime.utcnow)

    assignment = relationship("Assignment", back_populates="submissions")
    marking = relationship("Marking", back_populates="submission", uselist=False, cascade="all, delete-orphan")


class Marking(Base):
    """The marked result of a submission: overall score plus per-question detail."""

    __tablename__ = "markings"

    id = Column(String, primary_key=True)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=True)
    subject = Column(String, nullable=False)
    marks_awarded = Column(Float)
    marks_available = Column(Float)
    percentage = Column(Float)
    overall_feedback = Column(Text)
    strengths = Column(JSON)  # List of strings
    weaknesses = Column(JSON)  # List of strings
    weak_topics = Column(JSON)  # List of topic names — drives retest generation
    marked_by = Column(String, default="ai")  # ai, parent
    model = Column(String)
    langfuse_trace_id = Column(String)
    marked_at = Column(DateTime, default=datetime.utcnow)

    submission = relationship("Submission", back_populates="marking")
    question_marks = relationship(
        "QuestionMark",
        back_populates="marking",
        cascade="all, delete-orphan",
        order_by="QuestionMark.order_index",
    )


class QuestionMark(Base):
    """One question's worth of marking detail."""

    __tablename__ = "question_marks"

    id = Column(String, primary_key=True)
    marking_id = Column(String, ForeignKey("markings.id"), nullable=False)
    paper_question_id = Column(String, ForeignKey("paper_questions.id"), nullable=True)
    order_index = Column(Integer, nullable=False)
    question_number = Column(String)
    question_text = Column(Text)
    student_answer = Column(Text)
    expected_answer = Column(Text)
    marks_awarded = Column(Float, default=0)
    marks_available = Column(Float, default=1)
    verdict = Column(String)  # correct, partial, incorrect, not_attempted
    feedback = Column(Text)
    topic = Column(String)

    marking = relationship("Marking", back_populates="question_marks")


class TopicMastery(Base):
    """
    Rolling per-topic performance for a child, recalculated as markings and
    retests come in. This is what the retest button reads from.
    """

    __tablename__ = "topic_mastery"

    id = Column(String, primary_key=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    attempts = Column(Integer, default=0)
    marks_awarded = Column(Float, default=0)
    marks_available = Column(Float, default=0)
    mastery_pct = Column(Float)
    status = Column(String, default="weak")  # weak, developing, secure
    last_assessed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoreLogEntry(Base):
    """
    The score log from the tracker spreadsheet: every test result against the
    year-group average, so the gap can be charted over time.
    """

    __tablename__ = "score_log"

    id = Column(String, primary_key=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    subject = Column(String, nullable=False)
    label = Column(String, nullable=False)  # e.g. "Summer 2026 (non-calc)"
    score_pct = Column(Float)
    year_average_pct = Column(Float)
    source = Column(String, default="manual")  # report, marking, retest, manual
    marking_id = Column(String, ForeignKey("markings.id"), nullable=True)
    notes = Column(Text)
    recorded_at = Column(DateTime, default=datetime.utcnow)

