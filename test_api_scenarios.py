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

import pytest
from fastapi.testclient import TestClient

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
    assert "isCorrect" in data
    assert "correctAnswer" in data
    print(f"✓ Submitted answer - Correct: {data['isCorrect']}, Expected: {data['correctAnswer']}")
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
        questions_answered += 1
    
    # 4. Get summary
    summary_response = client.get(f"/api/runs/{run_id}/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert len(summary["questions"]) == questions_answered
    
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
    assert "isCorrect" in data
    assert "correctAnswer" in data
    assert "explanation" in data
    explanation_text = data.get('explanation') or 'N/A'
    explanation_preview = explanation_text[:50] if explanation_text else 'N/A'
    print(f"✓ AI marking works - Result: {data['isCorrect']}, Explanation: {explanation_preview}...")


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

