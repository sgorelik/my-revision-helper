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
from io import BytesIO
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from temporalio.client import Client

from .workflows import RevisionWorkflow

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
    studentAnswer: str
    isCorrect: bool
    correctAnswer: str
    explanation: Optional[str] = None


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


# ---------- FastAPI app setup ----------

app = FastAPI()

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
    Can be configured via AI_CONTEXT environment variable, or uses a sensible default.
    """
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


def get_marking_context() -> str:
    """
    Get context specifically for marking/evaluation.
    
    This is separate from question generation context to ensure marking
    doesn't include revision-specific content or file knowledge.
    
    Returns:
        String containing marking-specific instructions.
    """
    return (
        "You are a fair and thorough tutor grading a student's answer. "
        "Evaluate the answer based solely on the question asked. "
        "Be fair but thorough - partial credit may be appropriate for partially correct answers. "
        "Provide clear explanations for why an answer is correct or incorrect."
    )


# Maximum file size: 10MB (OpenAI Vision API has limits)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


async def extract_text_from_image(file: UploadFile, client: Any) -> Optional[str]:
    """
    Extract text from an uploaded image using OpenAI Vision API.
    
    Args:
        file: Uploaded file (should be an image)
        client: OpenAI client instance
        
    Returns:
        Extracted text, or None if extraction fails
    """
    try:
        # Read file content
        contents = await file.read()
        
        # Check file size
        if len(contents) > MAX_FILE_SIZE:
            logger.warning(f"File {file.filename} exceeds maximum size of {MAX_FILE_SIZE / (1024*1024)}MB")
            return None
        
        # Encode to base64 for OpenAI Vision API
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Determine image format from content type or file extension
        content_type = file.content_type or ""
        if "jpeg" in content_type or "jpg" in content_type:
            image_format = "image/jpeg"
        elif "png" in content_type:
            image_format = "image/png"
        elif "gif" in content_type:
            image_format = "image/gif"
        elif "webp" in content_type:
            image_format = "image/webp"
        else:
            # Try to infer from filename
            filename = file.filename or ""
            if filename.lower().endswith(('.jpg', '.jpeg')):
                image_format = "image/jpeg"
            elif filename.lower().endswith('.png'):
                image_format = "image/png"
            else:
                image_format = "image/jpeg"  # Default assumption
        
        # Use OpenAI Vision API to extract text
        response = client.chat.completions.create(
            model="gpt-4o",  # gpt-4o has vision capabilities
            messages=[
                {
                    "role": "system",
                    "content": "You are a text extraction assistant. Extract all text from the image accurately, preserving formatting and structure. Return only the extracted text, no explanations.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this image. Preserve the structure and formatting as much as possible.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_format};base64,{base64_image}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=2000,
        )
        
        extracted_text = response.choices[0].message.content
        logger.info(f"Extracted {len(extracted_text)} characters from image {file.filename}")
        return extracted_text
        
    except Exception as e:
        logger.error(f"Failed to extract text from image {file.filename}: {e}", exc_info=True)
        return None


async def process_uploaded_files(files: List[UploadFile]) -> Dict[str, str]:
    """
    Process uploaded files and extract text from images.
    
    Args:
        files: List of uploaded files
        
    Returns:
        Dictionary mapping filename to extracted text
    """
    if not files:
        return {}
    
    client = get_openai_client()
    if not client:
        logger.warning("OpenAI client not available - cannot extract text from images")
        return {}
    
    extracted_texts = {}
    skipped_files = []
    
    for file in files:
        # Check if it's an image file
        content_type = file.content_type or ""
        filename = file.filename or "unknown"
        
        # Check file size before processing
        # Note: We need to read the file to check size, but we'll read it again in extract_text_from_image
        # For now, we'll let extract_text_from_image handle the size check
        
        if any(img_type in content_type for img_type in ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]):
            logger.info(f"Processing image file: {filename}")
            text = await extract_text_from_image(file, client)
            if text:
                extracted_texts[filename] = text
            else:
                skipped_files.append(f"{filename} (extraction failed or file too large)")
        else:
            skipped_files.append(f"{filename} (not an image file)")
            logger.warning(f"Skipping non-image file: {filename} (type: {content_type})")
    
    if skipped_files:
        logger.info(f"Skipped {len(skipped_files)} file(s): {', '.join(skipped_files)}")
    
    return extracted_texts


# ---------- Endpoints used by the React frontend ----------

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/revisions", response_model=RevisionCreateResponse)
async def create_revision(
    name: str = Form(...),
    subject: str = Form(...),
    description: str = Form(""),
    desiredQuestionCount: int = Form(...),
    accuracyThreshold: int = Form(...),
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
        Uploaded image files are processed using OpenAI Vision API to extract text.
        The extracted text is combined with the description and used for question generation.
        Supported image formats: JPEG, PNG, GIF, WebP
    """
    topics_list = json.loads(topics) if topics else []
    revision_id = str(uuid.uuid4())

    # Process uploaded files to extract text
    extracted_texts = {}
    if files:
        logger.info(f"Processing {len(files)} uploaded file(s)")
        extracted_texts = await process_uploaded_files(files)
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
            combined_description or None,  # description
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

    # Persist the revision definition in-memory for the MVP
    revision_def = RevisionCreateResponse(
        id=revision_id,
        name=name,
        subject=subject,
        topics=topics_list,
        description=combined_description or None,  # Use combined description
        desiredQuestionCount=desiredQuestionCount,
        accuracyThreshold=accuracyThreshold,
        uploadedFiles=[f.filename for f in files] if files else None,
        extractedTextPreview=extracted_preview,
    )
    
    # Store with extracted texts for future reference
    revision_data = revision_def.model_dump()
    revision_data["extractedTexts"] = extracted_texts
    REVISION_DEFS[revision_id] = revision_data

    return revision_def


@app.get("/api/revisions", response_model=List[RevisionCreateResponse])
async def list_revisions() -> List[RevisionCreateResponse]:
    """
    List all configured revision definitions.
    """
    return [RevisionCreateResponse(**r) for r in REVISION_DEFS.values()]


@app.post("/api/revisions/{revision_id}/runs", response_model=RevisionRun)
async def start_run(revision_id: str) -> RevisionRun:
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
    if revision_id not in REVISION_DEFS:
        # In real code, you'd raise HTTPException(status_code=404)
        raise ValueError(f"Unknown revision_id {revision_id!r}")

    run_id = str(uuid.uuid4())
    run = RevisionRun(id=run_id, revisionId=revision_id, status="running")
    REVISION_RUNS[run_id] = run.model_dump()

    # Default fallback questions
    questions: List[dict] = [
        {"id": "q1", "text": "What is 2 + 2?"},
        {"id": "q2", "text": "What is 3 × 5?"},
    ]

    # If OpenAI is configured, try to generate questions from the revision description
    client = get_openai_client()
    rev_def = REVISION_DEFS.get(revision_id) or {}
    description = rev_def.get("description") or ""
    desired_count = int(rev_def.get("desiredQuestionCount") or 2)

    if not client:
        logger.warning("OpenAI client not available - using fallback questions")
    elif not description:
        logger.warning(f"No description provided for revision {revision_id} - using fallback questions")
    else:
        try:
            logger.info(f"Generating {desired_count} questions for revision {revision_id} with description: {description[:100]}...")
            general_context = get_ai_context()
            prompt = (
                f"{general_context}\n\n"
                "Generate concise practice questions for a student "
                "based on the following revision description. "
                "Return each question on its own line, with no numbering or extra text.\n\n"
                f"Revision description:\n{description}\n\n"
                f"Number of questions: {desired_count}"
            )
            response = client.chat.completions.create(
                model=get_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You generate short, clear study questions only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=desired_count * 64,
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            logger.info(f"OpenAI response received: {content[:200]}...")
            lines = [ln.strip("- ").strip() for ln in (content or "").splitlines()]
            lines = [ln for ln in lines if ln]
            if lines:
                questions = [
                    {"id": f"q{i+1}", "text": text}
                    for i, text in enumerate(lines[:desired_count])
                ]
                logger.info(f"Successfully generated {len(questions)} questions")
            else:
                logger.warning("OpenAI returned empty response - using fallback questions")
        except Exception as e:
            # Fall back to default questions on any failure
            logger.error(f"OpenAI question generation failed: {e}", exc_info=True)

    RUN_QUESTIONS[run_id] = questions
    RUN_ANSWERS[run_id] = []

    return run


@app.get("/api/revisions/{revision_id}/runs", response_model=List[RevisionRun])
async def list_runs_for_revision(revision_id: str) -> List[RevisionRun]:
    """
    List all runs for a given revision.
    """
    return [
        RevisionRun(**run)
        for run in REVISION_RUNS.values()
        if run["revisionId"] == revision_id
    ]


@app.get("/api/runs", response_model=List[RevisionRun])
async def list_runs() -> List[RevisionRun]:
    """
    List all runs across all revisions.
    """
    return [RevisionRun(**run) for run in REVISION_RUNS.values()]


@app.get("/api/runs/{run_id}/next-question", response_model=Question | None)
async def get_next_question(run_id: str):
    """
    Return the next question for this run, or None if finished.
    """
    questions = RUN_QUESTIONS.get(run_id, [])
    answers = RUN_ANSWERS.get(run_id, [])
    if len(answers) >= len(questions):
        return None
    q = questions[len(answers)]
    return Question(id=q["id"], text=q["text"])


@app.post("/api/runs/{run_id}/answers", response_model=AnswerResult)
async def submit_answer(run_id: str, payload: AnswerRequest):
    """
    Submit and mark a student's answer to a question.

    This endpoint:
    1. Receives the student's answer
    2. Uses OpenAI to mark it (if available) or falls back to simple matching
    3. Returns correctness, correct answer, and explanation
    4. Stores the result for summary generation

    Args:
        run_id: ID of the run this answer belongs to
        payload: AnswerRequest with questionId and answer text

    Returns:
        AnswerResult with marking details

    Note:
        AI marking uses the general AI_CONTEXT plus question-specific context.
        Falls back to simple string matching if OpenAI is unavailable.
    """
    # Try AI-based marking if OpenAI is configured
    client = get_openai_client()
    question_text = ""
    for q in RUN_QUESTIONS.get(run_id, []):
        if q.get("id") == payload.questionId:
            question_text = q.get("text", "")
            break

    if not client:
        logger.warning(f"OpenAI client not available for marking question {payload.questionId} - using fallback")
    elif not question_text:
        logger.warning(f"No question text found for {payload.questionId} - using fallback")
    
    if client and question_text:
        try:
            # Use marking-specific context (no revision content or file knowledge)
            marking_context = get_marking_context()
            prompt = (
                f"{marking_context}\n\n"
                "Question: " + question_text + "\n"
                "Student answer: " + payload.answer + "\n\n"
                "Respond in strict JSON with keys: is_correct (true/false), "
                "correct_answer (string), explanation (string). No extra text."
            )
            
            # Log full input for debugging
            logger.info("=" * 80)
            logger.info("MARKING REQUEST - Full Input:")
            logger.info(f"Question ID: {payload.questionId}")
            logger.info(f"Question: {question_text}")
            logger.info(f"Student Answer: {payload.answer}")
            logger.info(f"Marking Context: {marking_context}")
            logger.info(f"Full Prompt:\n{prompt}")
            logger.info("=" * 80)
            
            system_message = "You are a tutor who returns only valid JSON."
            logger.info(f"System Message: {system_message}")
            logger.info(f"Model: {get_openai_model()}")
            
            response = client.chat.completions.create(
                model=get_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": system_message,
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256,
                temperature=0.0,
            )
            content = response.choices[0].message.content or ""
            
            # Log full output for debugging
            logger.info("=" * 80)
            logger.info("MARKING RESPONSE - Full Output:")
            logger.info(f"Raw Response: {content}")
            logger.info(f"Response Length: {len(content)} characters")
            logger.info("=" * 80)
            
            data = json.loads(content)
            result = AnswerResult(
                questionId=payload.questionId,
                studentAnswer=payload.answer,
                isCorrect=bool(data.get("is_correct")),
                correctAnswer=str(data.get("correct_answer") or ""),
                explanation=data.get("explanation") or None,
            )
            logger.info(f"Parsed Result: isCorrect={result.isCorrect}, correctAnswer={result.correctAnswer}, explanation={result.explanation}")
        except Exception as e:
            # Fallback to simple correctness heuristic if parsing or API call fails
            logger.error(f"OpenAI marking failed: {e}", exc_info=True)
            logger.warning("Falling back to simple arithmetic marking")
            correct_map = {"q1": "4", "q2": "15"}
            correct_answer = correct_map.get(payload.questionId, "")
            is_correct = payload.answer.strip() == correct_answer
            result = AnswerResult(
                questionId=payload.questionId,
                studentAnswer=payload.answer,
                isCorrect=bool(correct_answer) and is_correct,
                correctAnswer=correct_answer,
                explanation=None,
            )
    else:
        # No OpenAI: use simple arithmetic placeholders
        logger.info(f"Using fallback marking for question {payload.questionId}")
        correct_map = {"q1": "4", "q2": "15"}
        correct_answer = correct_map.get(payload.questionId, "")
        is_correct = payload.answer.strip() == correct_answer
        result = AnswerResult(
            questionId=payload.questionId,
            studentAnswer=payload.answer,
            isCorrect=bool(correct_answer) and is_correct,
            correctAnswer=correct_answer,
            explanation=None,
        )
    
    # Store and return the result
    RUN_ANSWERS.setdefault(run_id, []).append(result.model_dump())
    return result


@app.get("/api/runs/{run_id}/summary", response_model=RevisionSummary)
async def get_summary(run_id: str):
    """
    Summarise all answered questions for this run.
    """
    answers_raw = RUN_ANSWERS.get(run_id, [])
    answers = [AnswerResult(**a) for a in answers_raw]
    if answers:
        accuracy = 100.0 * sum(1 for a in answers if a.isCorrect) / len(answers)
    else:
        accuracy = 0.0

    return RevisionSummary(
        revisionId=REVISION_RUNS.get(run_id, {}).get("revisionId", ""),
        questions=answers,
        overallAccuracy=accuracy,
    )


# Serve static files from frontend build (for production deployment)
# This allows the FastAPI server to serve the React frontend
# IMPORTANT: This must be added AFTER all API routes are defined
frontend_build_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_build_path):
    # Mount static assets (JS, CSS, images)
    assets_path = os.path.join(frontend_build_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
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
        
        # Serve index.html for all frontend routes (React Router handles client-side routing)
        index_path = os.path.join(frontend_build_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not built"}