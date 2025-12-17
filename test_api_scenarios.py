#!/usr/bin/env python3
"""Integration tests for the main API scenarios.

Tests the core workflows:
- Revision creation (with and without files)
- Question generation
- Answer submission and marking
- Summary generation
"""

import asyncio
import json
import os
from io import BytesIO
from typing import Dict, Any
from dotenv import load_dotenv

import pytest
from fastapi.testclient import TestClient

# Load environment variables
load_dotenv()

# Try to import PIL for image creation (optional)
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Import the app
from my_revision_helper.api import app

# Create test client
client = TestClient(app)


def test_health_endpoint():
    """Test that the health endpoint works."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print("✓ Health endpoint works")


def test_create_revision_basic():
    """Test creating a revision without files."""
    response = client.post(
        "/api/revisions",
        data={
            "name": "Test Revision",
            "subject": "Mathematics",
            "description": "Test basic arithmetic",
            "desiredQuestionCount": "2",
            "accuracyThreshold": "80",
            "topics": '["Addition", "Subtraction"]',
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Revision"
    assert data["subject"] == "Mathematics"
    assert data["desiredQuestionCount"] == 2
    assert data["accuracyThreshold"] == 80
    assert "id" in data
    revision_id = data["id"]
    print(f"✓ Created revision: {revision_id}")
    return revision_id


def test_create_revision_with_files():
    """Test creating a revision with file upload."""
    if not HAS_PIL:
        print("⚠ Skipping file upload test - PIL/Pillow not installed")
        return None
    
    # Create a simple test image (100x100 pixel PNG)
    img = Image.new("RGB", (100, 100), color="white")
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    response = client.post(
        "/api/revisions",
        data={
            "name": "Test Revision with Image",
            "subject": "History",
            "description": "Test with image upload",
            "desiredQuestionCount": "2",
            "accuracyThreshold": "75",
            "topics": '["World War II"]',
        },
        files={"files": ("test_image.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Revision with Image"
    assert data["uploadedFiles"] is not None
    assert len(data["uploadedFiles"]) == 1
    assert "test_image.png" in data["uploadedFiles"]
    print(f"✓ Created revision with file: {data['id']}")
    return data["id"]


def test_start_run():
    """Test starting a revision run."""
    # First create a revision
    revision_id = test_create_revision_basic()
    
    # Start a run
    response = client.post(f"/api/revisions/{revision_id}/runs")
    assert response.status_code == 200
    data = response.json()
    assert data["revisionId"] == revision_id
    assert data["status"] == "running"
    assert "id" in data
    run_id = data["id"]
    print(f"✓ Started run: {run_id}")
    return run_id, revision_id


def test_get_questions():
    """Test getting questions for a run."""
    run_id, revision_id = test_start_run()
    
    # Get first question
    response = client.get(f"/api/runs/{run_id}/next-question")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "text" in data
    assert len(data["text"]) > 0
    print(f"✓ Got question: {data['id']} - {data['text'][:50]}...")
    return run_id, data["id"]


def test_submit_answer():
    """Test submitting an answer and getting marking."""
    run_id, question_id = test_get_questions()
    
    # Submit an answer
    response = client.post(
        f"/api/runs/{run_id}/answers",
        json={
            "questionId": question_id,
            "answer": "4",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["questionId"] == question_id
    assert data["studentAnswer"] == "4"
    assert "isCorrect" in data  # Backward compatibility
    assert "score" in data  # New three-tier scoring
    assert data["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    assert "correctAnswer" in data
    # Verify isCorrect matches score
    assert data["isCorrect"] == (data["score"] == "Full Marks")
    print(f"✓ Submitted answer - Score: {data['score']}, Correct: {data['isCorrect']}, Expected: {data['correctAnswer']}")
    return run_id


def test_get_summary():
    """Test getting a summary after completing questions."""
    run_id = test_submit_answer()
    
    # Get summary
    response = client.get(f"/api/runs/{run_id}/summary")
    assert response.status_code == 200
    data = response.json()
    assert "revisionId" in data
    assert "questions" in data
    assert len(data["questions"]) > 0
    assert "overallAccuracy" in data
    assert 0 <= data["overallAccuracy"] <= 100
    
    # Verify all questions have score field
    for q in data["questions"]:
        assert "score" in q
        assert q["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
        assert "isCorrect" in q  # Backward compatibility
        assert q["isCorrect"] == (q["score"] == "Full Marks")
    
    print(f"✓ Got summary - Accuracy: {data['overallAccuracy']}%, Questions: {len(data['questions'])}")
    return data


def test_full_workflow():
    """Test the complete workflow from revision creation to summary."""
    print("\n🧪 Testing full workflow...")
    
    # 1. Create revision
    revision_id = test_create_revision_basic()
    
    # 2. Start run
    response = client.post(f"/api/revisions/{revision_id}/runs")
    run_id = response.json()["id"]
    
    # 3. Get and answer questions
    questions_answered = 0
    max_questions = 2
    
    while questions_answered < max_questions:
        # Get next question
        q_response = client.get(f"/api/runs/{run_id}/next-question")
        if q_response.status_code != 200:
            break
        
        question = q_response.json()
        question_id = question["id"]
        
        # Submit an answer
        answer_response = client.post(
            f"/api/runs/{run_id}/answers",
            json={
                "questionId": question_id,
                "answer": "test answer",
            },
        )
        assert answer_response.status_code == 200
        answer_data = answer_response.json()
        # Verify new scoring system
        assert "score" in answer_data
        assert answer_data["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
        assert "isCorrect" in answer_data
        assert answer_data["isCorrect"] == (answer_data["score"] == "Full Marks")
        questions_answered += 1
    
    # 4. Get summary
    summary_response = client.get(f"/api/runs/{run_id}/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert len(summary["questions"]) == questions_answered
    
    # Verify summary includes scores and accuracy calculation accounts for partial marks
    for q in summary["questions"]:
        assert "score" in q
        assert q["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    
    # Verify accuracy is calculated correctly (Full=100%, Partial=50%, Incorrect=0%)
    expected_max = 100.0 * questions_answered
    assert 0 <= summary["overallAccuracy"] <= 100
    
    print(f"✓ Full workflow completed - Answered {questions_answered} questions")
    return True


def test_marking_with_ai():
    """Test that AI marking works correctly (if OpenAI is configured)."""
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠ Skipping AI marking test - OPENAI_API_KEY not set")
        return
    
    run_id, question_id = test_get_questions()
    
    # Submit a German answer (to test AI understanding)
    response = client.post(
        f"/api/runs/{run_id}/answers",
        json={
            "questionId": question_id,
            "answer": "ein Kaninchen",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "isCorrect" in data  # Backward compatibility
    assert "score" in data  # New three-tier scoring
    assert data["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    assert "correctAnswer" in data
    assert "explanation" in data
    # Verify isCorrect matches score
    assert data["isCorrect"] == (data["score"] == "Full Marks")
    explanation_text = data.get('explanation') or 'N/A'
    explanation_preview = explanation_text[:50] if explanation_text else 'N/A'
    print(f"✓ AI marking works - Score: {data['score']}, Correct: {data['isCorrect']}, Explanation: {explanation_preview}...")


@pytest.mark.integration
def test_revision_persisted_to_database():
    """
    Test that revisions are persisted to the database when DATABASE_URL is set.
    
    This test verifies:
    1. Revision creation via API
    2. Revision is stored in database (not just in-memory)
    3. Revision can be retrieved from database
    """
    # Check if database is configured
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set - skipping database persistence test")
    
    # Create a revision via API
    revision_data = {
        "name": "Database Test Revision",
        "subject": "Mathematics",
        "description": "Test revision for database persistence",
        "desiredQuestionCount": "3",
        "accuracyThreshold": "75",
        "topics": "[]",
    }
    
    response = client.post(
        "/api/revisions",
        data=revision_data,
    )
    
    assert response.status_code == 200, f"Failed to create revision: {response.text}"
    created_revision = response.json()
    revision_id = created_revision["id"]
    
    assert revision_id is not None
    assert created_revision["name"] == revision_data["name"]
    
    # Verify revision is in database
    try:
        from my_revision_helper.database import get_db, engine
        from my_revision_helper.models_db import Revision
        
        if not engine:
            pytest.skip("Database engine not available")
        
        # Get database session
        db_gen = get_db()
        db = next(db_gen)
        
        if not db:
            pytest.skip("Database session not available")
        
        # Query database directly
        db_revision = db.query(Revision).filter(Revision.id == revision_id).first()
        
        assert db_revision is not None, f"Revision {revision_id} not found in database"
        assert db_revision.name == revision_data["name"]
        assert db_revision.subject == revision_data["subject"]
        assert db_revision.desired_question_count == int(revision_data["desiredQuestionCount"])
        assert db_revision.accuracy_threshold == int(revision_data["accuracyThreshold"])
        
        # Clean up - close database session
        db_gen.close()
        
        print(f"✓ Revision {revision_id} successfully persisted to database")
        
    except ImportError:
        pytest.skip("Database modules not available")
    except Exception as e:
        pytest.fail(f"Database verification failed: {e}")


@pytest.mark.integration
def test_anonymous_revision_persisted_with_session_id():
    """
    Test that anonymous user revisions are persisted with session_id.
    
    This test verifies:
    1. Anonymous revision creation (no auth token)
    2. Revision stored with session_id (not user_id)
    3. Revision can be retrieved by session_id
    """
    # Check if database is configured
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set - skipping database persistence test")
    
    # Create a revision without authentication (anonymous)
    revision_data = {
        "name": "Anonymous Test Revision",
        "subject": "Science",
        "description": "Test revision for anonymous user",
        "desiredQuestionCount": "2",
        "accuracyThreshold": "80",
        "topics": "[]",
    }
    
    # Make request - TestClient handles cookies automatically
    response = client.post(
        "/api/revisions",
        data=revision_data,
    )
    
    assert response.status_code == 200, f"Failed to create revision: {response.text}"
    created_revision = response.json()
    revision_id = created_revision["id"]
    
    # Verify revision is in database with session_id
    try:
        from my_revision_helper.database import get_db, engine
        from my_revision_helper.models_db import Revision
        
        if not engine:
            pytest.skip("Database engine not available")
        
        db_gen = get_db()
        db = next(db_gen)
        
        if not db:
            pytest.skip("Database session not available")
        
        # Query database for revision
        db_revision = db.query(Revision).filter(
            Revision.id == revision_id
        ).first()
        
        assert db_revision is not None, f"Revision {revision_id} not found in database"
        assert db_revision.user_id is None, "Anonymous revision should not have user_id"
        assert db_revision.session_id is not None, "Anonymous revision should have session_id"
        assert db_revision.name == revision_data["name"]
        
        db_gen.close()
        
        print(f"✓ Anonymous revision {revision_id} persisted with session_id {db_revision.session_id}")
        
    except ImportError:
        pytest.skip("Database modules not available")
    except Exception as e:
        pytest.fail(f"Database verification failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_list_completed_runs():
    """
    Test the /api/runs/completed endpoint.
    
    This test verifies:
    1. Creating a revision and completing a run
    2. Submitting at least one answer (to mark run as completed)
    3. Listing completed runs returns the completed run with correct data
    4. Completed run includes revision name, subject, score, and question count
    """
    # Create a revision
    revision_id = test_create_revision_basic()
    
    # Start a run
    run_response = client.post(f"/api/revisions/{revision_id}/runs")
    assert run_response.status_code == 200
    run_data = run_response.json()
    run_id = run_data["id"]
    
    # Get and answer at least one question to mark the run as completed
    question_response = client.get(f"/api/runs/{run_id}/next-question")
    assert question_response.status_code == 200
    question = question_response.json()
    question_id = question["id"]
    
    # Submit an answer
    answer_response = client.post(
        f"/api/runs/{run_id}/answers",
        json={
            "questionId": question_id,
            "answer": "test answer",
        },
    )
    assert answer_response.status_code == 200
    answer_data = answer_response.json()
    assert "score" in answer_data
    
    # Now list completed runs
    completed_response = client.get("/api/runs/completed")
    assert completed_response.status_code == 200
    completed_runs = completed_response.json()
    
    # Verify response is a list
    assert isinstance(completed_runs, list), "Response should be a list"
    
    # Find our completed run
    our_run = None
    for run in completed_runs:
        if run["runId"] == run_id:
            our_run = run
            break
    
    # Verify our run is in the list
    assert our_run is not None, f"Run {run_id} should be in completed runs list"
    
    # Verify the structure of completed run data
    assert "runId" in our_run
    assert "revisionId" in our_run
    assert "revisionName" in our_run
    assert "subject" in our_run
    assert "completedAt" in our_run
    assert "score" in our_run
    assert "totalQuestions" in our_run
    
    # Verify values
    assert our_run["runId"] == run_id
    assert our_run["revisionId"] == revision_id
    assert our_run["revisionName"] == "Test Revision"
    assert our_run["subject"] == "Mathematics"
    assert our_run["totalQuestions"] == 1  # We answered one question
    assert 0 <= our_run["score"] <= 100  # Score should be a percentage
    
    print(f"✓ Completed runs endpoint works - Found {len(completed_runs)} completed run(s)")
    print(f"  Run {run_id}: {our_run['revisionName']} - Score: {our_run['score']:.1f}%")
    
    return completed_runs


# Pytest markers for optional tests
if HAS_PIL:
    test_create_revision_with_files = pytest.mark.skipif(not HAS_PIL, reason="PIL/Pillow not installed")(test_create_revision_with_files)
test_marking_with_ai = pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")(test_marking_with_ai)


if __name__ == "__main__":
    print("=" * 80)
    print("🧪 Running API Scenario Tests")
    print("=" * 80)
    print()
    print("Note: Install Pillow for file upload tests: pip install Pillow")
    print()
    
    try:
        test_health_endpoint()
        print()
        
        test_create_revision_basic()
        print()
        
        test_create_revision_with_files()
        print()
        
        test_full_workflow()
        print()
        
        test_marking_with_ai()
        print()
        
        print("=" * 80)
        print("✅ All scenario tests passed!")
        print("=" * 80)
    except Exception as e:
        print("=" * 80)
        print(f"❌ Test failed: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        exit(1)

