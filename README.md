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
   - **Desired Question Count**: Number of questions to generate
   - **Accuracy Threshold**: Target accuracy percentage

2. Click "Create Revision"

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

### Running Tests

```bash
pytest
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
- [ ] Persistent database integration
- [ ] User authentication
- [ ] File upload processing
- [ ] Voice input for answers
- [ ] Image scanning for handwritten work

## License

[Specify your license here]

## Contributing

[Add contribution guidelines as needed]
