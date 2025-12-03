# My Revision Helper - Architecture Specification

## Overview

My Revision Helper is an AI-powered educational tool that helps students practice and test their knowledge through dynamically generated questions and intelligent answer marking. The system uses a three-tier architecture: React frontend, FastAPI backend, and Temporal workflows for orchestration.

## System Architecture

```
┌─────────────────┐
│  React Frontend │
│   (Port 5173)   │
└────────┬────────┘
         │ HTTP/REST
         ▼
┌─────────────────┐
│  FastAPI Backend│
│   (Port 8000)   │
└────────┬────────┘
         │
         ├─────────────────┐
         ▼                 ▼
┌─────────────────┐  ┌──────────────┐
│  Temporal       │  │   OpenAI     │
│  Workflows      │  │   API        │
│  (Port 7233)    │  │              │
└─────────────────┘  └──────────────┘
```

## Components

### 1. Frontend (`frontend/`)

**Technology Stack:**
- React 19 with TypeScript
- Vite for build tooling
- Single-page application (SPA)

**Key Features:**
- **Revision Setup Page**: Form to configure new revisions (name, subject, topics, description, question count, accuracy threshold)
- **Run Revision Page**: Interactive question/answer interface
- **Summary View**: Displays results with overall accuracy and per-question feedback

**State Management:**
- React hooks (`useState`) for local component state
- API calls via `fetch` to backend endpoints

**API Integration:**
- Base URL: `http://localhost:8000/api`
- All endpoints return JSON
- Error handling via try/catch with user-facing messages

### 2. Backend API (`my_revision_helper/api.py`)

**Technology Stack:**
- FastAPI for HTTP server
- Pydantic for request/response validation
- Python-dotenv for environment configuration

**Storage (MVP):**
- In-memory dictionaries for:
  - `REVISION_DEFS`: Revision definitions
  - `REVISION_RUNS`: Run/session records
  - `RUN_QUESTIONS`: Questions per run
  - `RUN_ANSWERS`: Answers per run

**Note:** Production should replace in-memory storage with a persistent database.

**API Endpoints:**

#### Revision Management
- `POST /api/revisions` - Create a new revision definition
- `GET /api/revisions` - List all revisions

#### Run Management
- `POST /api/revisions/{revision_id}/runs` - Start a new run
- `GET /api/revisions/{revision_id}/runs` - List runs for a revision
- `GET /api/runs` - List all runs

#### Question/Answer Flow
- `GET /api/runs/{run_id}/next-question` - Get next question (returns `null` when complete)
- `POST /api/runs/{run_id}/answers` - Submit and mark an answer
- `GET /api/runs/{run_id}/summary` - Get summary of all answers

**AI Integration:**
- Question generation via OpenAI when `OPENAI_API_KEY` is set
- Answer marking via OpenAI with structured JSON responses
- Graceful fallback to preset questions/marking if AI unavailable

### 3. Temporal Workflows (`my_revision_helper/workflows.py`)

**Current State:**
- Basic `RevisionWorkflow` that creates revision tasks
- Workflow is started on revision creation but not yet deeply integrated

**Future Integration:**
- Question generation workflow (orchestrates AI calls)
- Marking workflow (handles answer evaluation)
- Session management workflow (tracks run state)

**Activities (`my_revision_helper/activities.py`):**
- `create_revision_task`: Creates revision with optional AI suggestions
- Future: `generate_questions`, `mark_answer` activities

### 4. Worker (`my_revision_helper/worker.py`)

**Purpose:**
- Hosts Temporal workflows and activities
- Connects to Temporal server (default: `localhost:7233`)
- Runs continuously to process workflow tasks

**Configuration:**
- `TEMPORAL_TARGET`: Temporal server address
- `TEMPORAL_TASK_QUEUE`: Task queue name (default: `revision-helper-queue`)

## Data Models

### Revision Definition
```python
{
    "id": "uuid",
    "name": "string",
    "subject": "string",
    "topics": ["string"],
    "description": "string (optional)",
    "desiredQuestionCount": int,
    "accuracyThreshold": int (0-100)
}
```

### Run/Session
```python
{
    "id": "uuid",
    "revisionId": "uuid",
    "status": "running" | "completed"
}
```

### Question
```python
{
    "id": "q1",
    "text": "What is 2 + 2?"
}
```

### Answer Result
```python
{
    "questionId": "q1",
    "studentAnswer": "4",
    "isCorrect": true,
    "correctAnswer": "4",
    "explanation": "2 + 2 equals 4" (optional)
}
```

### Summary
```python
{
    "revisionId": "uuid",
    "questions": [AnswerResult, ...],
    "overallAccuracy": 85.5
}
```

## AI Configuration

### Environment Variables

**Required (for AI features):**
- `OPENAI_API_KEY`: Your OpenAI API key

**Optional:**
- `OPENAI_MODEL`: Model to use (default: `gpt-4o-mini`)
  - Valid models: `gpt-4o-mini`, `gpt-4o`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`
- `AI_CONTEXT`: General instructions for all AI prompts
  - Default: Encouraging tutor persona with fair marking guidelines

### AI Prompt Structure

**Question Generation:**
1. General context (from `AI_CONTEXT`)
2. Task-specific instructions
3. Revision description
4. Desired question count

**Answer Marking:**
1. General context (from `AI_CONTEXT`)
2. Grading instructions
3. Question text
4. Student answer
5. Request for JSON response: `{is_correct, correct_answer, explanation}`

## Workflow

### Creating and Running a Revision

1. **User creates revision** (`POST /api/revisions`)
   - Frontend sends form data
   - Backend creates revision definition
   - Backend starts Temporal workflow (for future use)
   - Returns revision ID

2. **User starts a run** (`POST /api/revisions/{id}/runs`)
   - Backend generates questions (AI or fallback)
   - Creates run record
   - Returns run ID

3. **User answers questions** (loop)
   - `GET /api/runs/{run_id}/next-question` → Get question
   - User types answer
   - `POST /api/runs/{run_id}/answers` → Submit and get marking
   - Repeat until `next-question` returns `null`

4. **User views summary** (`GET /api/runs/{run_id}/summary`)
   - Backend calculates overall accuracy
   - Returns all questions with results

## Deployment

### Development Setup

1. **Backend:**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Set up .env file
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   AI_CONTEXT=...
   
   # Start Temporal (if using)
   temporal server start-dev
   
   # Start worker (in separate terminal)
   python -m my_revision_helper.worker
   
   # Start API server
   uvicorn my_revision_helper.api:app --reload
   ```

2. **Frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

### Production Considerations

**Current Limitations (MVP):**
- In-memory storage (data lost on restart)
- No authentication/authorization
- No rate limiting
- CORS allows localhost only
- No persistent file storage

**Production Requirements:**
- Replace in-memory storage with database (PostgreSQL recommended)
- Add authentication (JWT, OAuth, etc.)
- Implement rate limiting
- Configure CORS for production domain
- Add file storage (S3, local filesystem, etc.)
- Add monitoring/logging (Sentry, DataDog, etc.)
- Deploy Temporal to production cluster
- Add CI/CD pipeline

## Future Enhancements

### Short-term
- [ ] Move question generation to Temporal workflow
- [ ] Move marking to Temporal activity
- [ ] Add file upload processing (extract text from PDFs, images)
- [ ] Improve question generation prompts
- [ ] Add question difficulty levels

### Medium-term
- [ ] Persistent database integration
- [ ] User authentication and multi-user support
- [ ] Revision history and analytics
- [ ] Voice input for answers
- [ ] Image scanning for handwritten work

### Long-term
- [ ] Multi-agent question review pipeline
- [ ] Adaptive difficulty based on performance
- [ ] Collaborative revision sessions
- [ ] Integration with learning management systems

## Security Considerations

**Current State:**
- No authentication (anyone can create/access revisions)
- API keys in environment variables (good)
- CORS restricted to localhost (good for dev)

**Production Needs:**
- User authentication and authorization
- API key rotation
- Input validation and sanitization
- Rate limiting per user
- HTTPS/TLS encryption
- Secure file upload handling

## Testing

**Current:**
- Bootstrap test (`test_bootstrap.py`) verifies basic setup
- Manual testing via frontend

**Future:**
- Unit tests for API endpoints
- Integration tests for AI workflows
- E2E tests for frontend flows
- Load testing for concurrent users

## Monitoring and Logging

**Current:**
- Python logging to stdout (INFO level)
- Logs include: OpenAI calls, errors, fallbacks

**Future:**
- Structured logging (JSON format)
- Log aggregation (ELK, CloudWatch, etc.)
- Metrics collection (Prometheus, DataDog)
- Error tracking (Sentry)
- Performance monitoring

## License

[Specify your license here]

## Contributors

[Add contributors as needed]

