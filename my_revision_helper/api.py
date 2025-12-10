"""
FastAPI HTTP API layer for My Revision Helper.

This module provides REST endpoints for the frontend to interact with the revision
system. It handles:
- Revision definition management (create, list)
- Run/session management (start, list)
- Question generation (via OpenAI when available)
- Answer submission and AI-powered marking
- Summary generation

The API uses in-memory storage for the MVP. In production, this should be replaced
with a persistent database.

Environment Variables:
    OPENAI_API_KEY: API key for OpenAI (optional, enables AI features)
    OPENAI_MODEL: Model to use (defaults to gpt-4o-mini)
    AI_CONTEXT: General context/instructions for all AI prompts
    TEMPORAL_TARGET: Temporal server address (defaults to localhost:7233)
    TEMPORAL_TASK_QUEUE: Task queue name (defaults to revision-helper-queue)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, Depends, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from temporalio.client import Client
from sqlalchemy.orm import Session

from .workflows import RevisionWorkflow
from .file_processing import process_uploaded_files
from .auth import get_current_user_optional
from .database import get_db, init_db
from .storage import StorageAdapter, get_or_create_user
from .langfuse_client import (
    fetch_prompt,
    render_prompt,
    create_trace,
    create_generation,
    get_langfuse_environment,
)

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:  # Optional OpenAI client
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


# ---------- In-memory MVP state (demo only, not production-safe) ----------
#
# NOTE: These in-memory dictionaries are used for the MVP. In production, replace
# with a persistent database (PostgreSQL, MongoDB, etc.) or use Temporal's durable
# state management.

# Stored revision definitions keyed by revision_id
# Each entry contains: id, name, subject, topics, description, desiredQuestionCount, accuracyThreshold, extractedTexts
REVISION_DEFS: Dict[str, dict] = {}

# Stored runs keyed by run_id
# Each entry contains: id, revisionId, status
REVISION_RUNS: Dict[str, dict] = {}

# Per-run questions and answers
# RUN_QUESTIONS[run_id] = [{"id": "q1", "text": "..."}, ...]
# RUN_ANSWERS[run_id] = [AnswerResult dict, ...]
RUN_QUESTIONS: Dict[str, List[dict]] = {}
RUN_ANSWERS: Dict[str, List[dict]] = {}


# ---------- Pydantic models for HTTP layer ----------


class RevisionCreateResponse(BaseModel):
    """Response model for revision creation and listing."""

    id: str
    name: str
    subject: str
    topics: List[str]
    description: Optional[str] = None
    desiredQuestionCount: int
    accuracyThreshold: int
    uploadedFiles: Optional[List[str]] = None  # List of uploaded file names
    extractedTextPreview: Optional[str] = None  # Preview of extracted text (first 200 chars)


class Question(BaseModel):
    """A single question in a revision run."""

    id: str
    text: str


class AnswerRequest(BaseModel):
    """Request payload for submitting an answer."""

    questionId: str
    answer: str


class AnswerResult(BaseModel):
    """Result of marking a student's answer."""

    questionId: str
    questionText: Optional[str] = None  # The question text for display in summary
    studentAnswer: str
    isCorrect: bool  # Kept for backward compatibility
    score: str  # "Full Marks", "Partial Marks", or "Incorrect"
    correctAnswer: str
    explanation: Optional[str] = None
    error: Optional[str] = None  # Error message if marking failed


class RevisionSummary(BaseModel):
    """Summary of all answers for a completed run."""

    revisionId: str
    questions: List[AnswerResult]
    overallAccuracy: float


class RevisionRun(BaseModel):
    """A single run/session of a revision."""

    id: str
    revisionId: str
    status: str


class CompletedRun(BaseModel):
    """A completed revision run with summary data."""

    runId: str
    revisionId: str
    revisionName: str
    subject: str
    completedAt: str
    score: float
    totalQuestions: int
    threshold: int


# ---------- FastAPI app setup ----------

app = FastAPI()

# Add validation error handler for better debugging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    logger.error(f"Validation error on {request.url.path}: {exc.errors()}")
    try:
        body = await request.body()
        logger.error(f"Request body: {body.decode()[:500] if body else 'Empty'}")
    except Exception:
        logger.error("Could not read request body")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc.body) if hasattr(exc, 'body') else None}
    )

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on application startup."""
    logger.info("🚀 Application startup - initializing database...")
    try:
        init_db()
    except Exception as e:
        logger.error(f"❌ Failed to initialize database on startup: {e}", exc_info=True)

# CORS configuration - can be set via ALLOWED_ORIGINS env var (comma-separated)
# For Railway deployment, Railway will provide a domain like *.railway.app
# You can also use "*" for development, but restrict in production!
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]

# Allow Railway domains by default if ALLOWED_ORIGINS not explicitly set
if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain not in allowed_origins:
        allowed_origins.append(f"https://{railway_domain}")
        allowed_origins.append(f"http://{railway_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_temporal_client() -> Client:
    """
    Get a connected Temporal client.

    Returns:
        A connected Temporal Client instance.

    Raises:
        RuntimeError: If Temporal SDK is not installed or connection fails.
    """
    try:
        from temporalio.client import Client
    except ImportError:
        raise RuntimeError("Temporal SDK not installed")
    
    target = os.getenv("TEMPORAL_TARGET", "localhost:7233")
    return await Client.connect(target)


def get_openai_client() -> Any | None:
    """Return an OpenAI client if the SDK and API key are available."""
    if OpenAI is None:
        logger.warning("OpenAI SDK not installed")
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY environment variable not set")
        return None
    try:
        logger.info("OpenAI client created successfully")
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to create OpenAI client: {e}", exc_info=True)
        return None


def get_openai_model() -> str:
    """Get the OpenAI model name from env, with a safe fallback."""
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # Common valid models - add more as needed
    valid_models = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ]
    if model not in valid_models:
        logger.warning(
            f"Model '{model}' may not be valid. Falling back to 'gpt-4o-mini'. "
            f"Valid models include: {', '.join(valid_models)}"
        )
        return "gpt-4o-mini"
    return model


def get_ai_context() -> str:
    """
    Get general context/instructions to always include in AI prompts.
    Tries to fetch from Langfuse first, then falls back to AI_CONTEXT env var or default.
    """
    # Try to fetch from Langfuse first
    langfuse_prompt_data = fetch_prompt("general-context")
    if langfuse_prompt_data and langfuse_prompt_data.get("prompt"):
        context = langfuse_prompt_data["prompt"]
        logger.info("Using general-context prompt from Langfuse")
        return context
    
    # Fallback to environment variable or default
    context = os.getenv(
        "AI_CONTEXT",
        (
            "You are a helpful and encouraging tutor. "
            "Provide clear, educational feedback. "
            "Questions should be appropriate for students and test understanding of key concepts. "
            "When marking, be fair but thorough - partial credit may be appropriate for partially correct answers."
        ),
    )
    return context


def get_marking_context(revision_context: Optional[str] = None) -> str:
    """
    Get context specifically for marking/evaluation.
    Fetches base marking context and revision context template from Langfuse,
    then combines them if revision_context is provided.
    
    Args:
        revision_context: Optional revision description and extracted text from uploaded files.
                          If provided, marking will be based on what was actually available to the student.
    
    Returns:
        String containing marking-specific instructions with three-tier scoring guidance.
    """
    # Try to fetch base marking context from Langfuse
    marking_context_data = fetch_prompt("marking-context")
    if marking_context_data and marking_context_data.get("prompt"):
        base_instructions = marking_context_data["prompt"]
        logger.info("Using marking-context prompt from Langfuse")
    else:
        # Fallback to hardcoded base instructions
        base_instructions = (
            "You are a fair and thorough tutor grading a student's answer. "
            "Evaluate the answer based on what the student was actually expected to know from the provided material. "
            "\n\n"
            "SCORING GUIDELINES:\n"
            "- Full Marks: Award when the answer is completely or nearly correct, demonstrates full understanding, "
            "and includes all required elements that were available in the revision material. The answer should be "
            "accurate, complete, and show clear comprehension of the concept as presented in the material.\n"
            "- Partial Marks: Award when the answer shows some understanding but is incomplete, "
            "partially correct, or missing key elements. CRITICAL: If the revision material did not contain "
            "sufficient depth or detail for the student to have known a specific piece of information, do NOT "
            "penalize them for missing it. Award Partial Marks if they demonstrate understanding of what WAS "
            "in the material, even if their answer is incomplete. Examples include: correct concept but wrong "
            "details (only if those details were in the material), correct answer but missing explanation "
            "(if explanation was in material), partially correct calculations, or correct approach but minor errors.\n"
            "- Incorrect: Award when the answer is fundamentally wrong, shows misunderstanding of "
            "the concept as presented in the material, or is completely off-topic. The answer demonstrates "
            "little to no understanding of what was provided.\n"
            "\n"
            "IMPORTANT FAIRNESS RULES:\n"
            "- If revision material was provided, use it as a reference, but do NOT restrict answers to only what was in the material.\n"
            "- CRITICAL: Do NOT penalize students if they provide a correct answer using information NOT in the supplied materials. "
            "If a student gives a generally correct answer (even if the specific example or detail wasn't in the material), "
            "award Full Marks. For example, if the PDF discussed specific gases but the student correctly answers with a different "
            "gas that wasn't mentioned, this is still a correct answer and should receive Full Marks.\n"
            "- Do NOT penalize students for information that was NOT in the provided revision material when their answer is missing details.\n"
            "- If the material lacks depth on a topic, be lenient - award Partial Marks or even Full Marks if "
            "the student demonstrates understanding of what WAS available, even if the answer seems incomplete "
            "from a general knowledge perspective.\n"
            "- Be generous with Partial Marks when students show genuine understanding of the provided material, "
            "even if their answer isn't perfect.\n"
            "- Award Full Marks for any answer that is generally correct and demonstrates proper understanding, "
            "regardless of whether the specific information was in the revision material.\n"
            "\n"
            "Provide clear explanations for the score awarded, referencing what was (or wasn't) in the revision material."
        )
    
    # If revision_context is provided, fetch and render the revision context template
    if revision_context:
        revision_template_data = fetch_prompt("revision-context-template")
        if revision_template_data and revision_template_data.get("prompt"):
            revision_template = revision_template_data["prompt"]
            # Render the template with the actual revision_context content
            revision_section = render_prompt(
                revision_template,
                {"revision_context": revision_context}
            )
            logger.info("Using revision-context-template prompt from Langfuse")
        else:
            # Fallback to hardcoded revision context section
            revision_section = (
                "REVISION MATERIAL PROVIDED:\n"
                "The following is the revision material (description and/or extracted text from uploaded files) "
                "that was available to the student:\n\n"
                f"{revision_context}\n\n"
                "When evaluating the student's answer:\n"
                "- Use the material above as a reference for what was provided, but do NOT restrict correct answers to only what's in the material.\n"
                "- If a student provides a correct answer using information NOT in the material (e.g., mentions a gas not in the PDF but still correctly answers the question), "
                "award Full Marks - they demonstrated correct understanding even if from their own knowledge.\n"
                "- If the student's answer is incomplete but the material itself didn't provide complete information, "
                "be lenient in your scoring - award Partial Marks or Full Marks based on understanding shown.\n"
                "- Award marks based on correctness and understanding, not on whether every detail matches the material exactly."
            )
        
        return f"{base_instructions}\n\n{revision_section}"
    
    return base_instructions




# ---------- Subject definitions (shared between frontend and backend) ----------

# Valid subjects that can be used to differentiate input/output handling
def get_marking_json_instructions(subject: Optional[str] = None) -> str:
    """
    Get JSON response format instructions for AI marking.
    
    This can be customized based on subject or other context to provide
    subject-specific guidance on response format.
    
    Args:
        subject: Optional subject name (e.g., "Mathematics", "Science") for subject-specific instructions
    
    Returns:
        String containing JSON response format instructions
    """
    base_instructions = (
        "Respond in strict JSON with keys: "
        "score (string: 'Full Marks', 'Partial Marks', or 'Incorrect'), "
        "is_correct (boolean: true for Full Marks, false otherwise), "
        "correct_answer (string), explanation (string). "
        "IMPORTANT: You MUST always provide an explanation. "
        "The explanation should clearly justify the score awarded. "
        "For Partial Marks, explain what was correct and what was missing or incorrect. "
        "For Incorrect, explain why it's wrong and what the correct answer is. "
        "For Full Marks, explain why the answer is completely correct. No extra text."
    )
    
    # Subject-specific customizations can be added here
    if subject:
        # Example: Mathematics might need specific instructions
        if subject.lower() in ["mathematics", "math"]:
            base_instructions += (
                " For mathematical answers, show working or reasoning when relevant."
            )
        # Add more subject-specific instructions as needed
    
    return base_instructions

VALID_SUBJECTS = [
    "Mathematics",
    "Science",
    "English",
    "History",
    "Geography",
    "Art",
    "Music",
    "Physical Education",
    "Computer Science",
    "Foreign Languages",
    "Other",
]

# ---------- Endpoints used by the React frontend ----------

def get_session_id(session_id: Optional[str] = Cookie(None)) -> str:
    """Get or generate session ID for anonymous users."""
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/subjects")
async def get_subjects():
    """Get list of valid subjects."""
    return {"subjects": VALID_SUBJECTS}


@app.get("/api/user/me")
async def get_current_user_info(
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
):
    """
    Get current user info - returns authentication status.
    
    Returns:
        - If authenticated: user info with authenticated: true
        - If not authenticated: authenticated: false
    """
    if not user:
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name"),
        "picture": user.get("picture"),
    }


@app.post("/api/revisions", response_model=RevisionCreateResponse)
async def create_revision(
    response: Response,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
    name: str = Form(...),
    subject: str = Form(...),
    description: str = Form(""),
    desiredQuestionCount: str = Form(...),  # Accept as string, convert to int
    accuracyThreshold: str = Form(...),  # Accept as string, convert to int
    topics: str = Form("[]"),
    files: List[UploadFile] = File(default_factory=list),
):
    """
    Create a new revision definition.

    This endpoint:
    1. Processes uploaded image files to extract text using OCR (OpenAI Vision API)
    2. Combines extracted text with the provided description
    3. Creates a new revision with the provided configuration
    4. Starts a Temporal workflow for the revision (for future orchestration)
    5. Stores the revision definition in-memory

    Args:
        name: Name/title of the revision
        subject: Subject area (e.g., "Mathematics", "History")
        description: Detailed description of what to study (used for AI question generation)
        desiredQuestionCount: Number of questions to generate for runs
        accuracyThreshold: Target accuracy percentage (0-100)
        topics: JSON array of topic areas (e.g., '["Algebra", "Geometry"]')
        files: Optional uploaded image files (JPEG, PNG, etc.) - text will be extracted via OCR

    Returns:
        RevisionCreateResponse with the created revision's details

    Note:
        Uploaded files are processed to extract text:
        - Images (JPEG, PNG, GIF, WebP): Uses OpenAI Vision API for OCR
        - PDFs: Uses pdfplumber library
        - PowerPoint (PPTX): Uses python-pptx library
        The extracted text is combined with the description and used for question generation.
    """
    # Convert string form values to appropriate types
    try:
        desired_question_count = int(desiredQuestionCount)
    except (ValueError, TypeError):
        logger.error(f"Invalid desiredQuestionCount: {desiredQuestionCount}")
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid desiredQuestionCount: must be an integer, got {desiredQuestionCount!r}")
    
    try:
        accuracy_threshold = int(accuracyThreshold)
    except (ValueError, TypeError):
        logger.error(f"Invalid accuracyThreshold: {accuracyThreshold}")
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid accuracyThreshold: must be an integer, got {accuracyThreshold!r}")
    
    # Parse topics JSON
    try:
        topics_list = json.loads(topics) if topics and topics != "[]" else []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid topics JSON: {topics}, error: {e}")
        topics_list = []
    
    revision_id = str(uuid.uuid4())

    # Process uploaded files to extract text
    extracted_texts = {}
    if files:
        logger.info(f"Processing {len(files)} uploaded file(s)")
        client = get_openai_client()
        extracted_texts = await process_uploaded_files(files, client)
        if extracted_texts:
            logger.info(f"Successfully extracted text from {len(extracted_texts)} file(s)")

    # Combine description with extracted text from files
    combined_description = description or ""
    if extracted_texts:
        file_texts = "\n\n".join([f"Text from {filename}:\n{text}" for filename, text in extracted_texts.items()])
        if combined_description:
            combined_description = f"{combined_description}\n\n{file_texts}"
        else:
            combined_description = file_texts

    # Start a workflow for this revision definition (can be expanded later)
    # Note: If Temporal is not available, we continue without it (workflow is optional for MVP)
    try:
        client = await get_temporal_client()
        await client.start_workflow(
            RevisionWorkflow.run,
            revision_id,  # task_id
            name,  # title
            combined_description or None,  # description (optional)
            id=revision_id,
            task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "revision-helper-queue"),
        )
        logger.info(f"Started Temporal workflow for revision {revision_id}")
    except Exception as e:
        # Don't fail revision creation if Temporal is unavailable
        logger.warning(f"Could not start Temporal workflow (Temporal may not be running): {e}")
        logger.info("Continuing with revision creation without workflow...")

    # Create preview of extracted text (first 200 characters)
    extracted_preview = None
    if extracted_texts:
        all_text = " ".join(extracted_texts.values())
        extracted_preview = all_text[:200] + ("..." if len(all_text) > 200 else "")

    # Use storage adapter to persist (database if available, otherwise in-memory)
    storage = StorageAdapter(user, db, session_id)
    
    revision_data = {
        "id": revision_id,
        "name": name,
        "subject": subject,
        "topics": topics_list,
        "description": combined_description or None,
        "desiredQuestionCount": desired_question_count,
        "accuracyThreshold": accuracy_threshold,
        "extractedTexts": extracted_texts,
        "uploadedFiles": [f.filename for f in files] if files else None,
        "extractedTextPreview": extracted_preview,
    }
    
    revision = storage.create_revision(revision_data)
    
    # Set session cookie for anonymous users
    if not user:
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=86400 * 30,  # 30 days
            httponly=True,
            samesite="lax"
        )

    return RevisionCreateResponse(**revision)


@app.get("/api/revisions", response_model=List[RevisionCreateResponse])
async def list_revisions(
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[RevisionCreateResponse]:
    """
    List revision definitions.
    
    - Authenticated users: see their own revisions (persisted)
    - Anonymous users: see revisions from current session only (not retrievable later)
    """
    storage = StorageAdapter(user, db, session_id)
    revisions = storage.list_revisions()
    return [RevisionCreateResponse(**r) for r in revisions]


@app.delete("/api/revisions/{revision_id}")
async def delete_revision(
    revision_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Delete a revision configuration.
    
    - Only authenticated users can delete revisions
    - Users can only delete revisions they created
    - Non-authenticated users cannot delete revisions
    """
    from fastapi import HTTPException
    
    # Only authenticated users can delete
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to delete revisions")
    
    storage = StorageAdapter(user, db, session_id)
    success = storage.delete_revision(revision_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Revision {revision_id} not found or you don't have permission to delete it")
    
    return {"message": f"Revision {revision_id} deleted successfully"}


@app.post("/api/revisions/{revision_id}/runs", response_model=RevisionRun)
async def start_run(
    revision_id: str,
    response: Response,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> RevisionRun:
    """
    Start a new run/session for a revision.

    This endpoint:
    1. Creates a new run associated with the revision
    2. Generates questions using OpenAI (if available) or falls back to preset questions
    3. Initializes empty answer storage for this run

    Args:
        revision_id: ID of the revision to run

    Returns:
        RevisionRun with the new run's ID and status

    Raises:
        ValueError: If revision_id doesn't exist

    Note:
        Question generation uses the revision's description and desiredQuestionCount.
        If OpenAI is unavailable or description is missing, falls back to simple
        arithmetic questions.
    """
    # Use storage adapter
    storage = StorageAdapter(user, db, session_id)
    
    # Check if revision exists and user/session has access
    revision = storage.get_revision(revision_id)
    if not revision:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Revision {revision_id} not found")

    run_id = str(uuid.uuid4())
    
    # Get revision data for question generation
    rev_def = revision

    # Default fallback questions (use run_id to ensure unique IDs)
    questions: List[dict] = [
        {"id": f"{run_id}-q1", "text": "What is 2 + 2?"},
        {"id": f"{run_id}-q2", "text": "What is 3 × 5?"},
    ]

    # If OpenAI is configured, try to generate questions from the revision description
    client = get_openai_client()
    description = rev_def.get("description") or ""
    desired_count = int(rev_def.get("desiredQuestionCount") or 2)

    error_message = None
    if not client:
        error_message = "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
        logger.error(error_message)
    elif not description:
        error_message = "No description provided for this revision. Please add a description or upload files with content."
        logger.error(error_message)
    else:
        try:
            logger.info(f"Generating {desired_count} questions for revision {revision_id} with description: {description[:100]}...")
            
            # Get user ID for tracing
            user_id = user.get("user_id") if user else None
            
            # Create Langfuse trace
            trace = create_trace(
                name="question-generation",
                user_id=user_id,
                revision_id=revision_id,
                run_id=run_id,
                metadata={
                    "desired_count": desired_count,
                    "subject": revision.get("subject") if revision else None,
                },
            )
            
            # Get subject for subject-specific prompts
            subject = revision.get("subject") if revision else None
            
            # Try to fetch prompt from Langfuse, fallback to hardcoded if not available
            # Will try subject-specific prompt first (e.g., 'question-generation-mathematics'),
            # then fall back to generic 'question-generation'
            langfuse_prompt_data = fetch_prompt("question-generation", subject=subject)
            
            if langfuse_prompt_data and langfuse_prompt_data.get("prompt"):
                # Use Langfuse prompt
                prompt_template = langfuse_prompt_data["prompt"]
                general_context = get_ai_context()
                prompt = render_prompt(
                    prompt_template,
                    {
                        "general_context": general_context,
                        "description": description,
                        "desired_count": desired_count,
                    },
                )
                system_message = "You generate short, clear study questions only."
                logger.info("Using Langfuse prompt for question generation")
            else:
                # Fallback to hardcoded prompt
                general_context = get_ai_context()
                prompt = (
                    f"{general_context}\n\n"
                    "Generate concise practice questions for a student "
                    "based on the following revision description. "
                    "Return each question on its own line, with no numbering or extra text.\n\n"
                    f"Revision description:\n{description}\n\n"
                    f"Number of questions: {desired_count}"
                )
                system_message = "You generate short, clear study questions only."
                logger.info("Using fallback prompt for question generation (Langfuse prompt not found)")
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ]
            
            model = get_openai_model()
            openai_response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=desired_count * 64,
                temperature=0.7,
            )
            content = openai_response.choices[0].message.content or ""
            
            # Log to Langfuse
            if trace:
                create_generation(
                    trace=trace,
                    name="openai-question-generation",
                    model=model,
                    input_data={"messages": messages},
                    output=content,
                    metadata={
                        "max_tokens": desired_count * 64,
                        "temperature": 0.7,
                    },
                )
                # End the trace after generation is complete
                try:
                    trace.end()
                    logger.debug("Ended Langfuse trace after generation")
                    # Flush one more time to ensure everything is sent
                    from .langfuse_client import get_langfuse
                    client = get_langfuse()
                    if client:
                        client.flush()
                except Exception as e:
                    logger.warning(f"Failed to end trace: {e}")
            
            logger.info(f"OpenAI response received: {content[:200]}...")
            lines = [ln.strip("- ").strip() for ln in (content or "").splitlines()]
            lines = [ln for ln in lines if ln]
            if lines:
                questions = [
                    {"id": f"{run_id}-q{i+1}", "text": text}
                    for i, text in enumerate(lines[:desired_count])
                ]
                logger.info(f"Successfully generated {len(questions)} questions")
            else:
                error_message = "OpenAI returned an empty response. Please try again or check your API configuration."
                logger.error(error_message)
        except Exception as e:
            # Return error instead of falling back
            error_message = f"Failed to generate questions: {str(e)}"
            logger.error(f"OpenAI question generation failed: {e}", exc_info=True)
    
    # If there was an error, store it as a special question so it can be displayed
    if error_message:
        questions = [
            {
                "id": "error",
                "text": f"ERROR: {error_message}",
                "error": error_message
            }
        ]

    # Store run and questions using storage adapter
    run_data = {
        "id": run_id,
        "revisionId": revision_id,
        "status": "running",
    }
    run = storage.create_run(run_data)
    storage.store_questions(run_id, questions)
    
    # Set session cookie for anonymous users
    if not user:
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=86400 * 30,  # 30 days
            httponly=True,
            samesite="lax"
        )

    return RevisionRun(**run)


@app.get("/api/revisions/{revision_id}/runs", response_model=List[RevisionRun])
async def list_runs_for_revision(
    revision_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[RevisionRun]:
    """
    List all runs for a given revision.
    """
    storage = StorageAdapter(user, db, session_id)
    # Note: This is a simplified implementation - in a full version,
    # we'd query runs by revision_id from the database
    # For now, we'll return empty list as this endpoint is not heavily used
    return []


@app.get("/api/runs", response_model=List[RevisionRun])
async def list_runs(
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[RevisionRun]:
    """
    List all runs across all revisions.
    Note: This endpoint is simplified - full implementation would query database.
    """
    # Note: This endpoint is not heavily used in the frontend
    # For now, return empty list - can be enhanced later if needed
    return []


@app.get("/api/runs/completed", response_model=List[CompletedRun])
async def list_completed_runs(
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
) -> List[CompletedRun]:
    """
    List all completed runs with summary data (revision name, score, etc.).
    
    - Only authenticated users can see completed runs
    - Non-authenticated users will receive an empty list
    """
    # Only authenticated users can see completed runs
    if not user:
        return []
    
    storage = StorageAdapter(user, db, session_id)
    completed_runs = storage.list_completed_runs()
    return [CompletedRun(**run) for run in completed_runs]


@app.get("/api/runs/{run_id}/question-count")
async def get_question_count(
    run_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Get the total number of questions for this run.
    """
    storage = StorageAdapter(user, db, session_id)
    questions = storage.get_questions(run_id)
    return {"totalQuestions": len(questions)}


@app.get("/api/runs/{run_id}/next-question", response_model=Question | None)
async def get_next_question(
    run_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Return the next question for this run, or None if finished.
    """
    storage = StorageAdapter(user, db, session_id)
    questions = storage.get_questions(run_id)
    answers = storage.get_answers(run_id)
    if len(answers) >= len(questions):
        return None
    q = questions[len(answers)]
    return Question(id=q["id"], text=q["text"])


@app.post("/api/runs/{run_id}/answers", response_model=AnswerResult)
async def submit_answer(
    run_id: str,
    payload: AnswerRequest,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Submit and mark a student's answer to a question.

    This endpoint:
    1. Receives the student's answer
    2. Retrieves revision context (description + extracted text from uploaded files)
    3. Uses OpenAI with RAG-style marking - evaluates based on what was actually provided
    4. Returns score (Full Marks/Partial Marks/Incorrect), correct answer, and explanation
    5. Stores the result for summary generation

    Args:
        run_id: ID of the run this answer belongs to
        payload: AnswerRequest with questionId and answer text

    Returns:
        AnswerResult with marking details including score field

    Note:
        AI marking uses RAG (Retrieval Augmented Generation) approach:
        - Includes revision description and extracted text from uploaded files
        - Evaluates answers based ONLY on what was actually provided to the student
        - Does NOT penalize students for information not in the revision material
        - Awards Partial Marks generously when material lacked depth
        Falls back to simple string matching if OpenAI is unavailable.
    """
    # Use storage adapter
    storage = StorageAdapter(user, db, session_id)
    
    # Get run to verify access and get revision_id
    run = storage.get_run(run_id)
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    revision_id = run["revisionId"]
    
    # Try AI-based marking if OpenAI is configured
    client = get_openai_client()
    question_text = ""
    questions = storage.get_questions(run_id)
    for q in questions:
        if q.get("id") == payload.questionId:
            question_text = q.get("text", "")
            break

    # Get revision context for RAG-style marking
    revision_context = None
    revision = storage.get_revision(revision_id)
    if revision:
        # Get the combined description (includes extracted text from files)
        revision_context = revision.get("description") or ""
        if not revision_context:
            # Fallback: try to reconstruct from extractedTexts
            extracted_texts = revision.get("extractedTexts", {})
            if extracted_texts:
                revision_context = "\n\n".join([
                    f"Text from {filename}:\n{text}"
                    for filename, text in extracted_texts.items()
                ])

    # Log diagnostic information
    logger.info(f"Marking request - Question ID: {payload.questionId}, Run ID: {run_id}")
    logger.info(f"OpenAI client available: {client is not None}")
    logger.info(f"Question text found: {bool(question_text)}")
    logger.info(f"Revision context available: {bool(revision_context)}")
    if question_text:
        logger.info(f"Question text: {question_text[:100]}...")
    if revision_context:
        logger.info(f"Revision context length: {len(revision_context)} characters")
    else:
        logger.warning(f"No question text found for questionId {payload.questionId} in run {run_id}")
        logger.warning(f"Available questions in run: {[q.get('id') for q in RUN_QUESTIONS.get(run_id, [])]}")

    if not client:
        logger.warning(f"OpenAI client not available for marking question {payload.questionId} - using fallback")
    elif not question_text:
        logger.warning(f"No question text found for {payload.questionId} - using fallback")
    
    if client and question_text:
        try:
            # Get user ID for tracing
            user_id = user.get("user_id") if user else None
            revision_id = run.get("revisionId") if run else None
            
            # Create Langfuse trace
            trace = create_trace(
                name="answer-marking",
                user_id=user_id,
                revision_id=revision_id,
                run_id=run_id,
                question_id=payload.questionId,
                metadata={
                    "subject": revision.get("subject") if revision else None,
                },
            )
            
            # Use marking context with revision material for RAG-style evaluation
            marking_context = get_marking_context(revision_context=revision_context)
            
            # Get subject for subject-specific prompts and JSON instructions
            subject = None
            if revision:
                subject = revision.get("subject")
            
            json_instructions = get_marking_json_instructions(subject=subject)
            
            # Try to fetch prompt from Langfuse, fallback to hardcoded if not available
            # Will try subject-specific prompt first (e.g., 'answer-marking-mathematics'),
            # then fall back to generic 'answer-marking'
            langfuse_prompt_data = fetch_prompt("answer-marking", subject=subject)
            
            if langfuse_prompt_data and langfuse_prompt_data.get("prompt"):
                # Use Langfuse prompt
                prompt_template = langfuse_prompt_data["prompt"]
                general_context = get_ai_context()
                prompt = render_prompt(
                    prompt_template,
                    {
                        "general_context": general_context,
                        "marking_context": marking_context,
                        "question": question_text,
                        "student_answer": payload.answer,
                        "json_instructions": json_instructions,
                    },
                )
                system_message = "You are a tutor who returns only valid JSON."
                logger.info("Using Langfuse prompt for answer marking")
            else:
                # Fallback to hardcoded prompt
                general_context = get_ai_context()
                prompt = (
                    f"{general_context}\n\n"
                    f"{marking_context}\n\n"
                    "Question: " + question_text + "\n"
                    "Student answer: " + payload.answer + "\n\n"
                    f"{json_instructions}"
                )
                system_message = "You are a tutor who returns only valid JSON."
                logger.info("Using fallback prompt for answer marking (Langfuse prompt not found)")
            
            # Log full input for debugging
            logger.info("=" * 80)
            logger.info("MARKING REQUEST - Full Input:")
            logger.info(f"Question ID: {payload.questionId}")
            logger.info(f"Question: {question_text}")
            logger.info(f"Student Answer: {payload.answer}")
            logger.info(f"Marking Context: {marking_context}")
            logger.info(f"Full Prompt:\n{prompt}")
            logger.info("=" * 80)
            
            logger.info(f"System Message: {system_message}")
            model = get_openai_model()
            logger.info(f"Model: {model}")
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ]
            
            openai_response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=256,
                temperature=0.0,
            )
            content = openai_response.choices[0].message.content or ""
            
            # Log to Langfuse
            if trace:
                create_generation(
                    trace=trace,
                    name="openai-answer-marking",
                    model=model,
                    input_data={"messages": messages},
                    output=content,
                    metadata={
                        "max_tokens": 256,
                        "temperature": 0.0,
                    },
                )
                # End the trace after generation is complete
                try:
                    trace.end()
                    logger.debug("Ended Langfuse trace after generation")
                    # Flush one more time to ensure everything is sent
                    from .langfuse_client import get_langfuse
                    client = get_langfuse()
                    if client:
                        client.flush()
                except Exception as e:
                    logger.warning(f"Failed to end trace: {e}")
            
            # Log full output for debugging
            logger.info("=" * 80)
            logger.info("MARKING RESPONSE - Full Output:")
            logger.info(f"Raw Response: {content}")
            logger.info(f"Response Length: {len(content)} characters")
            logger.info("=" * 80)
            
            # Try to parse JSON - OpenAI sometimes wraps it in markdown code blocks
            json_content = content.strip()
            
            # Remove markdown code blocks if present
            if json_content.startswith("```"):
                # Extract JSON from code block
                lines = json_content.split("\n")
                # Remove first line (```json or ```)
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                json_content = "\n".join(lines)
            
            # Try to find JSON object in the response
            try:
                # First, try direct parsing
                data = json.loads(json_content)
            except json.JSONDecodeError:
                # Try to extract JSON object from the text
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        logger.info(f"Extracted JSON from response: {json_match.group(0)[:200]}...")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse extracted JSON: {json_match.group(0)[:200]}")
                        raise
                else:
                    logger.error(f"No JSON object found in response: {content[:200]}")
                    raise
            explanation = data.get("explanation") or ""
            score = data.get("score", "").strip()
            
            # Validate and normalize score
            valid_scores = ["Full Marks", "Partial Marks", "Incorrect"]
            if score not in valid_scores:
                # Try to infer from is_correct if score is missing
                is_correct = bool(data.get("is_correct"))
                if is_correct:
                    score = "Full Marks"
                else:
                    # Default to Incorrect if we can't determine
                    score = "Incorrect"
                logger.warning(f"Invalid or missing score '{data.get('score')}', inferred '{score}' from is_correct={is_correct}")
            
            # Determine is_correct from score (for backward compatibility)
            is_correct = (score == "Full Marks")
            
            # Ensure we always have an explanation
            if not explanation:
                if score == "Full Marks":
                    explanation = "Your answer is completely correct!"
                elif score == "Partial Marks":
                    explanation = f"Your answer shows some understanding. The correct answer is: {data.get('correct_answer', 'N/A')}. Review what was missing or incorrect."
                else:  # Incorrect
                    explanation = f"The correct answer is: {data.get('correct_answer', 'N/A')}. Please review the question and try again."
            
            result = AnswerResult(
                questionId=payload.questionId,
                studentAnswer=payload.answer,
                isCorrect=is_correct,
                score=score,
                correctAnswer=str(data.get("correct_answer") or ""),
                explanation=explanation,
            )
            logger.info(f"Parsed Result: score={result.score}, isCorrect={result.isCorrect}, correctAnswer={result.correctAnswer}")
        except Exception as e:
            # Return error instead of falling back to static content
            error_message = f"Failed to mark answer using AI: {str(e)}"
            logger.error(f"OpenAI marking failed: {e}", exc_info=True)
            
            result = AnswerResult(
                questionId=payload.questionId,
                studentAnswer=payload.answer,
                isCorrect=False,
                score="Incorrect",
                correctAnswer="",
                explanation=None,
                error=error_message,
            )
    else:
        # No OpenAI or no question text: return error
        if not client:
            error_message = "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
        else:
            error_message = f"Question text not found for question ID {payload.questionId}. This may indicate a problem with question generation."
        
        logger.error(f"Marking failed: {error_message}")
        
        result = AnswerResult(
            questionId=payload.questionId,
            studentAnswer=payload.answer,
            isCorrect=False,
            score="Incorrect",
            correctAnswer="",
            explanation=None,
            error=error_message,
        )
    
    # Store answer using storage adapter
    storage.store_answer(run_id, result.model_dump())
    return result


@app.get("/api/runs/{run_id}/summary", response_model=RevisionSummary)
async def get_summary(
    run_id: str,
    user: Optional[Dict[str, str]] = Depends(get_current_user_optional),
    db: Optional[Session] = Depends(get_db),
    session_id: str = Depends(get_session_id),
):
    """
    Summarise all answered questions for this run.
    
    - Authenticated users can view summaries of their runs
    - Non-authenticated users can view summaries of runs in their current session
    - Non-authenticated users cannot view summaries from other sessions
    """
    from fastapi import HTTPException
    
    storage = StorageAdapter(user, db, session_id)
    
    # Verify run access (storage.get_run handles session-based access control)
    # For authenticated users: checks user_id
    # For anonymous users: checks session_id
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found or access denied")
    
    revision_id = run["revisionId"]
    
    # Get answers and questions
    answers_raw = storage.get_answers(run_id)
    questions = storage.get_questions(run_id)
    questions_dict = {q["id"]: q.get("text", "") for q in questions}
    
    # Enrich answers with question text
    enriched_answers = []
    for a in answers_raw:
        answer_dict = dict(a)
        # Add question text if available
        question_id = answer_dict.get("questionId")
        if question_id in questions_dict:
            answer_dict["questionText"] = questions_dict[question_id]
        elif answer_dict.get("questionText"):
            # Already has questionText from database
            pass
        enriched_answers.append(AnswerResult(**answer_dict))
    
    if enriched_answers:
        # Calculate accuracy: Full Marks = 100%, Partial Marks = 50%, Incorrect = 0%
        total_score = 0.0
        for a in enriched_answers:
            if a.score == "Full Marks":
                total_score += 100.0
            elif a.score == "Partial Marks":
                total_score += 50.0
            # Incorrect adds 0
        accuracy = total_score / len(enriched_answers) if enriched_answers else 0.0
    else:
        accuracy = 0.0

    return RevisionSummary(
        revisionId=revision_id,
        questions=enriched_answers,
        overallAccuracy=accuracy,
    )


# Serve static files from frontend build (for production deployment)
# This allows the FastAPI server to serve the React frontend
# IMPORTANT: This must be added AFTER all API routes are defined
frontend_build_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
logger.info(f"Frontend build path: {frontend_build_path}")
logger.info(f"Frontend build path exists: {os.path.exists(frontend_build_path)}")

if os.path.exists(frontend_build_path):
    # Mount static assets (JS, CSS, images)
    assets_path = os.path.join(frontend_build_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
        logger.info(f"Mounted static assets from: {assets_path}")
    else:
        logger.warning(f"Assets directory not found: {assets_path}")
    
    # Serve index.html for all non-API routes (catch-all must be last)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """
        Serve the React frontend for all non-API routes.
        This catch-all route must be defined last so API routes take precedence.
        """
        # Don't serve frontend for API routes (shouldn't reach here if routes are defined correctly)
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        
        # Check if it's a static file (like calculator-logo.png from public folder)
        # Vite copies files from public/ to dist/ root
        static_file_path = os.path.join(frontend_build_path, full_path)
        if os.path.isfile(static_file_path) and full_path != "index.html":
            logger.info(f"Serving static file: {static_file_path}")
            return FileResponse(static_file_path)
        
        # Serve index.html for all frontend routes (React Router handles client-side routing)
        index_path = os.path.join(frontend_build_path, "index.html")
        if os.path.exists(index_path):
            logger.info(f"Serving frontend from: {index_path}")
            return FileResponse(index_path)
        else:
            logger.error(f"Frontend index.html not found at: {index_path}")
            return {
                "error": "Frontend not built",
                "details": f"Expected index.html at {index_path}",
                "build_path": frontend_build_path,
                "build_path_exists": os.path.exists(frontend_build_path)
            }
else:
    logger.error(f"Frontend build directory not found: {frontend_build_path}")
    # Fallback: serve a simple message if frontend isn't built
    @app.get("/{full_path:path}")
    async def serve_frontend_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        return {
            "error": "Frontend not built",
            "details": f"Frontend build directory not found at {frontend_build_path}",
            "message": "Please ensure the frontend is built during deployment (npm run build in frontend/)"
        }