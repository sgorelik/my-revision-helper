# My Revision Helper

An AI-powered educational tool that helps students practice and test their knowledge through dynamically generated questions and intelligent answer marking.

## Overview

My Revision Helper is a full-stack application with:
- **React Frontend**: Interactive web interface for creating revisions and taking practice tests
- **FastAPI Backend**: REST API for revision management, question generation, and answer marking
- **Temporal Workflows**: Orchestration layer for durable, retryable workflows (currently basic, expanding)
- **OpenAI Integration**: AI-powered question generation and answer marking

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed architecture documentation.

```
Frontend (React) → Backend (FastAPI) → Temporal Workflows → OpenAI API
```

## Prerequisites

- Python 3.12+ (3.13 recommended)
- Node.js 18+ and npm
- [Temporal CLI](https://docs.temporal.io/cli) (optional, for workflow features)
- OpenAI API key (for AI features)

## Quick Start

### 1. Install Python Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Or using uv (recommended)
uv sync
source .venv/bin/activate  # On macOS/Linux
```

### 2. Set Up Environment Variables

Create a `.env` file in the project root:

```env
# Required for AI features
OPENAI_API_KEY=sk-your-key-here

# Optional AI configuration
OPENAI_MODEL=gpt-4o-mini
AI_CONTEXT=You are a helpful and encouraging tutor...

# Temporal configuration (optional)
TEMPORAL_TARGET=localhost:7233
TEMPORAL_TASK_QUEUE=revision-helper-queue
```

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 4. Start the Services

**Terminal 1 - Temporal Server** (optional, for workflow features):
```bash
temporal server start-dev
```

**Terminal 2 - Temporal Worker** (optional):
```bash
python -m my_revision_helper.worker
```

**Terminal 3 - Backend API**:
```bash
uvicorn my_revision_helper.api:app --reload
```

**Terminal 4 - Frontend**:
```bash
cd frontend
npm run dev
```

### 5. Access the Application

Open your browser to: `http://localhost:5173`

## Usage

### Creating a Revision

1. Fill out the revision setup form:
   - **Name**: Title of your revision
   - **Subject**: Subject area (e.g., "Mathematics")
   - **Topics**: Comma-separated topic areas
   - **Description**: Detailed description (used for AI question generation)
   - **Upload Images** (optional): Upload JPEG/PNG images containing text
     - Text is automatically extracted using OCR (OpenAI Vision API)
     - Extracted text is combined with your description for question generation
     - Maximum file size: 10MB per file
   - **Desired Question Count**: Number of questions to generate
   - **Accuracy Threshold**: Target accuracy percentage

2. Click "Create Revision"
   - If images are uploaded, they will be processed first
   - The revision will be created with the combined text from description and images

### Running a Revision

1. After creating a revision, a run automatically starts
2. Answer each question as it appears
3. Submit your answer to get immediate feedback
4. Continue through all questions
5. View the summary with overall accuracy and per-question results

## Project Structure

```
my_revision_helper/
├── my_revision_helper/        # Python package
│   ├── __init__.py
│   ├── api.py                 # FastAPI HTTP endpoints
│   ├── activities.py          # Temporal activities
│   ├── workflows.py           # Temporal workflows
│   ├── models.py              # Data models
│   ├── worker.py              # Temporal worker
│   ├── cli.py                 # CLI interface
│   ├── client_start.py        # Workflow client
│   └── client_interact.py     # Workflow interaction
├── frontend/                  # React frontend
│   ├── src/
│   │   └── App.tsx           # Main React component
│   └── package.json
├── requirements.txt           # Python dependencies
├── ARCHITECTURE.md           # Architecture documentation
└── README.md                 # This file
```

## API Endpoints

### Revision Management
- `POST /api/revisions` - Create a new revision
- `GET /api/revisions` - List all revisions

### Run Management
- `POST /api/revisions/{revision_id}/runs` - Start a new run
- `GET /api/revisions/{revision_id}/runs` - List runs for a revision
- `GET /api/runs` - List all runs

### Question/Answer Flow
- `GET /api/runs/{run_id}/next-question` - Get next question
- `POST /api/runs/{run_id}/answers` - Submit and mark an answer
- `GET /api/runs/{run_id}/summary` - Get summary of all answers

## Development

### Testing

#### End-to-End (E2E) Smoke Tests

We use [Playwright](https://playwright.dev/) for E2E smoke tests to ensure critical user flows work after UI changes.

**Quick Start:**

```bash
# From the frontend directory
cd frontend

# Run all E2E tests (headless)
npm run test:e2e

# Run tests with interactive UI
npm run test:e2e:ui

# Run tests in headed mode (see browser)
npm run test:e2e:headed
```

**Prerequisites:**
- Backend server must be running on port 8000
- Frontend must be built (tests use production build)

**Test Coverage:**
- Homepage load and form display
- Creating a revision
- Answering questions
- Viewing summary
- File upload UI
- Form validation
- Complete workflow end-to-end

See [README_TESTING.md](./README_TESTING.md) for detailed E2E testing documentation.

#### Backend API Tests

The project includes comprehensive test suites to verify functionality and catch regressions.

#### Test Files

- **`test_bootstrap.py`**: Verifies basic setup (imports, environment, Temporal connection)
- **`test_deployment.py`**: Checks deployment configuration (static files, CORS, environment variables)
- **`test_api_scenarios.py`**: Integration tests for core API workflows

#### Running Tests

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest test_api_scenarios.py -v
```

**Run specific test:**
```bash
pytest test_api_scenarios.py::test_health_endpoint -v
```

**Run tests directly (without pytest):**
```bash
python3 test_api_scenarios.py
python3 test_bootstrap.py
```

#### Test Coverage

The `test_api_scenarios.py` suite covers:

1. **Health Check** (`test_health_endpoint`)
   - Verifies the `/api/health` endpoint responds correctly

2. **Revision Creation** (`test_create_revision_basic`, `test_create_revision_with_files`)
   - Creates revisions with and without file uploads
   - Validates response structure and data persistence

3. **Run Management** (`test_start_run`)
   - Tests starting a revision run
   - Verifies run status and ID generation

4. **Question Flow** (`test_get_questions`)
   - Retrieves questions for a run
   - Validates question structure

5. **Answer Submission** (`test_submit_answer`)
   - Submits answers and verifies marking
   - Tests both AI marking and fallback behavior

6. **Summary Generation** (`test_get_summary`)
   - Retrieves completion summary
   - Validates accuracy calculations

7. **Full Workflow** (`test_full_workflow`)
   - End-to-end test: create → run → questions → answers → summary
   - Ensures all components work together

8. **AI Marking** (`test_marking_with_ai`)
   - Verifies AI-powered answer marking works correctly
   - Tests explanation generation
   - Only runs if `OPENAI_API_KEY` is set

#### Test Requirements

**Required:**
- `pytest` - Test framework
- `fastapi` - For `TestClient`
- `httpx` - HTTP client (installed with fastapi)

**Optional:**
- `Pillow` - For file upload tests (`pip install Pillow`)
  - If not installed, file upload tests are skipped

#### Test Environment

Tests use FastAPI's `TestClient` which:
- Runs in-process (no network calls)
- Isolates each test (fresh state)
- Fast execution
- No external dependencies required (except OpenAI for AI tests)

#### Example Test Output

```bash
$ pytest test_api_scenarios.py -v

============================= test session starts ==============================
test_api_scenarios.py::test_health_endpoint PASSED                       [ 11%]
test_api_scenarios.py::test_create_revision_basic PASSED                 [ 22%]
test_api_scenarios.py::test_create_revision_with_files SKIPPED           [ 33%]
test_api_scenarios.py::test_start_run PASSED                             [ 44%]
test_api_scenarios.py::test_get_questions PASSED                         [ 55%]
test_api_scenarios.py::test_submit_answer PASSED                         [ 66%]
test_api_scenarios.py::test_get_summary PASSED                           [ 77%]
test_api_scenarios.py::test_full_workflow PASSED                         [ 88%]
test_api_scenarios.py::test_marking_with_ai PASSED                       [100%]

============================== 8 passed, 1 skipped in 6.73s ===================
```

#### Writing New Tests

When adding new features, add corresponding tests:

1. **API Endpoints**: Add tests in `test_api_scenarios.py`
2. **Workflows**: Add tests in a new `test_workflows.py` file
3. **Utilities**: Add unit tests in `test_utils.py`

Example test structure:
```python
def test_new_feature():
    """Test description."""
    response = client.post("/api/new-endpoint", json={...})
    assert response.status_code == 200
    data = response.json()
    assert data["expected_field"] == "expected_value"
```

### Code Style

The project uses standard Python conventions. Consider using:
- `black` for code formatting
- `ruff` or `pylint` for linting
- `mypy` for type checking

### Adding Features

1. **New API Endpoints**: Add to `my_revision_helper/api.py`
2. **New Workflows**: Add to `my_revision_helper/workflows.py`
3. **New Activities**: Add to `my_revision_helper/activities.py`
4. **Frontend Changes**: Modify `frontend/src/App.tsx` or create new components

## Configuration

### AI Configuration

Customize AI behavior via environment variables:

- **`AI_CONTEXT`**: General instructions for all AI prompts
  ```env
  AI_CONTEXT=You are a math tutor for high school students. Focus on problem-solving techniques...
  ```

- **`OPENAI_MODEL`**: Model to use (default: `gpt-4o-mini`)
  ```env
  OPENAI_MODEL=gpt-4o
  ```

### Fallback Behavior

If OpenAI is unavailable:
- Question generation falls back to simple arithmetic questions
- Answer marking falls back to string matching
- The system remains functional for testing

## Troubleshooting

### Backend Issues

- **"OpenAI client not available"**: Check `OPENAI_API_KEY` in `.env`
- **"Model not found"**: Check `OPENAI_MODEL` is valid (see ARCHITECTURE.md)
- **Connection refused**: Ensure Temporal server is running (if using workflows)

### Frontend Issues

- **CORS errors**: Ensure backend is running on port 8000
- **API errors**: Check browser console and backend logs
- **Build errors**: Run `npm install` in `frontend/` directory

### General

- **Import errors**: Ensure virtual environment is activated
- **Port conflicts**: Change ports in `api.py` (backend) or `vite.config.ts` (frontend)

## Current Limitations (MVP)

- In-memory storage (data lost on restart)
- No authentication/authorization
- No rate limiting
- CORS allows localhost only
- No persistent file storage
- Basic Temporal integration (workflows started but not deeply used)

See [ARCHITECTURE.md](./ARCHITECTURE.md) for production considerations.

## Future Enhancements

- [ ] Move question generation to Temporal workflow
- [ ] Move marking to Temporal activity
- [ ] Persistent database integration (PostgreSQL)
- [ ] User authentication and authorization
- [x] File upload processing with OCR (✅ Implemented)
- [ ] Voice input for answers
- [ ] Image scanning for handwritten work
- [ ] Revision configuration persistence (save/load revisions)
- [ ] Multi-language support
- [ ] Question difficulty levels
- [ ] Progress tracking and analytics

## License

[Specify your license here]

## Contributing

[Add contribution guidelines as needed]
