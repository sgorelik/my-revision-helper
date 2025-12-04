#!/usr/bin/env python3
"""Tests specifically for the three-tier scoring system.

Tests:
- Score field validation
- Score to isCorrect mapping
- Accuracy calculation with partial marks
- All three score types (Full Marks, Partial Marks, Incorrect)
"""

import os
import pytest
from fastapi.testclient import TestClient

from my_revision_helper.api import app

client = TestClient(app)


def test_score_field_present():
    """Test that all answer results include the score field."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Create a revision
    revision_response = client.post(
        "/api/revisions",
        data={
            "name": "Scoring Test",
            "subject": "Mathematics",
            "description": "Test scoring system",
            "desiredQuestionCount": "1",
            "accuracyThreshold": "80",
            "topics": "[]",
        },
    )
    assert revision_response.status_code == 200
    revision_id = revision_response.json()["id"]
    
    # Start a run
    run_response = client.post(f"/api/revisions/{revision_id}/runs")
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]
    
    # Get a question
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
    data = answer_response.json()
    
    # Verify score field exists and is valid
    assert "score" in data
    assert data["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    assert "isCorrect" in data
    assert isinstance(data["isCorrect"], bool)
    
    # Verify isCorrect matches score
    assert data["isCorrect"] == (data["score"] == "Full Marks")
    
    print(f"✓ Score field present: {data['score']}, isCorrect: {data['isCorrect']}")


def test_accuracy_calculation_with_partial_marks():
    """Test that accuracy calculation correctly accounts for partial marks."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Create a revision
    revision_response = client.post(
        "/api/revisions",
        data={
            "name": "Accuracy Test",
            "subject": "Mathematics",
            "description": "Test accuracy calculation",
            "desiredQuestionCount": "3",
            "accuracyThreshold": "80",
            "topics": "[]",
        },
    )
    assert revision_response.status_code == 200
    revision_id = revision_response.json()["id"]
    
    # Start a run
    run_response = client.post(f"/api/revisions/{revision_id}/runs")
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]
    
    # Answer questions (we'll get whatever questions are generated)
    questions_answered = 0
    max_questions = 3
    
    while questions_answered < max_questions:
        question_response = client.get(f"/api/runs/{run_id}/next-question")
        if question_response.status_code != 200:
            break
        
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
        questions_answered += 1
    
    # Get summary
    summary_response = client.get(f"/api/runs/{run_id}/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    
    # Verify all questions have scores
    for q in summary["questions"]:
        assert "score" in q
        assert q["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    
    # Calculate expected accuracy manually
    total_score = 0.0
    for q in summary["questions"]:
        if q["score"] == "Full Marks":
            total_score += 100.0
        elif q["score"] == "Partial Marks":
            total_score += 50.0
        # Incorrect adds 0
    
    expected_accuracy = total_score / len(summary["questions"]) if summary["questions"] else 0.0
    
    # Verify accuracy matches (allow small floating point differences)
    assert abs(summary["overallAccuracy"] - expected_accuracy) < 0.01
    
    print(f"✓ Accuracy calculation correct: {summary['overallAccuracy']}% (expected: {expected_accuracy}%)")


def test_score_values():
    """Test that score values are always one of the three valid options."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Create a revision
    revision_response = client.post(
        "/api/revisions",
        data={
            "name": "Score Values Test",
            "subject": "Mathematics",
            "description": "Test score values",
            "desiredQuestionCount": "1",
            "accuracyThreshold": "80",
            "topics": "[]",
        },
    )
    assert revision_response.status_code == 200
    revision_id = revision_response.json()["id"]
    
    # Start a run
    run_response = client.post(f"/api/revisions/{revision_id}/runs")
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]
    
    # Get a question
    question_response = client.get(f"/api/runs/{run_id}/next-question")
    assert question_response.status_code == 200
    question = question_response.json()
    question_id = question["id"]
    
    # Submit an answer
    answer_response = client.post(
        f"/api/runs/{run_id}/answers",
        json={
            "questionId": question_id,
            "answer": "some answer",
        },
    )
    assert answer_response.status_code == 200
    data = answer_response.json()
    
    # Verify score is one of the valid values
    valid_scores = ["Full Marks", "Partial Marks", "Incorrect"]
    assert data["score"] in valid_scores, f"Score '{data['score']}' is not one of {valid_scores}"
    
    print(f"✓ Score value is valid: {data['score']}")


if __name__ == "__main__":
    print("=" * 80)
    print("🧪 Running Scoring System Tests")
    print("=" * 80)
    print()
    
    try:
        test_score_field_present()
        print()
        
        test_accuracy_calculation_with_partial_marks()
        print()
        
        test_score_values()
        print()
        
        print("=" * 80)
        print("✅ All scoring system tests passed!")
        print("=" * 80)
    except Exception as e:
        print("=" * 80)
        print(f"❌ Test failed: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        exit(1)


