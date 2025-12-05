#!/usr/bin/env python3
"""
End-to-end smoke test for the full application flow.

Tests:
1. Create revision (authenticated and anonymous)
2. Start run
3. Answer questions
4. Get summary
5. Verify data persistence in database
"""

import os
import sys
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def test_health():
    """Test health endpoint."""
    print("1. Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("   ✓ Health check passed")

def test_create_revision_anonymous():
    """Test creating a revision as anonymous user."""
    print("\n2. Testing revision creation (anonymous)...")
    
    data = {
        "name": "E2E Test Revision",
        "subject": "Mathematics",
        "description": "Test revision for end-to-end testing",
        "desiredQuestionCount": "3",
        "accuracyThreshold": "75",
        "topics": "[]",
    }
    
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/revisions", data=data, timeout=10)
    
    assert response.status_code == 200, f"Failed to create revision: {response.text}"
    revision = response.json()
    revision_id = revision["id"]
    
    assert revision["name"] == data["name"]
    assert revision["subject"] == data["subject"]
    print(f"   ✓ Created revision: {revision_id}")
    
    # Verify revision is in database
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            from my_revision_helper.database import get_db, engine
            from my_revision_helper.models_db import Revision
            
            if engine:
                db_gen = get_db()
                db = next(db_gen)
                if db:
                    db_revision = db.query(Revision).filter(Revision.id == revision_id).first()
                    assert db_revision is not None, "Revision not found in database"
                    assert db_revision.name == data["name"]
                    print("   ✓ Revision persisted to database")
                db_gen.close()
        except ImportError:
            pass
    
    # Get session_id from cookie
    session_id = None
    for cookie in session.cookies:
        if cookie.name == "session_id":
            session_id = cookie.value
            break
    
    assert session_id is not None, "Session ID cookie not set"
    print(f"   ✓ Session ID: {session_id}")
    
    return revision_id, session, session_id

def test_list_revisions(session):
    """Test listing revisions."""
    print("\n3. Testing list revisions...")
    
    response = session.get(f"{BASE_URL}/api/revisions", timeout=5)
    assert response.status_code == 200
    revisions = response.json()
    
    assert len(revisions) > 0, "No revisions found"
    print(f"   ✓ Found {len(revisions)} revision(s)")
    
    # Verify the revision we created is in the list
    revision_names = [r["name"] for r in revisions]
    assert "E2E Test Revision" in revision_names, "Created revision not in list"
    print("   ✓ Created revision found in list")
    
    return revisions[0]["id"]

def test_start_run(revision_id, session):
    """Test starting a revision run."""
    print("\n4. Testing start run...")
    
    response = session.post(f"{BASE_URL}/api/revisions/{revision_id}/runs", timeout=10)
    if response.status_code != 200:
        print(f"   ✗ Failed to start run: {response.status_code}")
        print(f"   Response: {response.text}")
        raise AssertionError(f"Failed to start run: {response.status_code} - {response.text}")
    
    run = response.json()
    run_id = run["id"]
    
    assert run["revisionId"] == revision_id
    assert run["status"] == "running"
    print(f"   ✓ Started run: {run_id}")
    
    return run_id

def test_get_question(run_id, session):
    """Test getting a question."""
    print("\n5. Testing get question...")
    
    response = session.get(f"{BASE_URL}/api/runs/{run_id}/next-question", timeout=10)
    assert response.status_code == 200
    question = response.json()
    
    assert "id" in question
    assert "text" in question
    assert len(question["text"]) > 0
    print(f"   ✓ Got question: {question['id']}")
    print(f"   Question: {question['text'][:50]}...")
    
    return question["id"], question["text"]

def test_submit_answer(run_id, question_id, session):
    """Test submitting an answer."""
    print("\n6. Testing submit answer...")
    
    answer_data = {
        "questionId": question_id,
        "answer": "test answer",
    }
    
    response = session.post(
        f"{BASE_URL}/api/runs/{run_id}/answers",
        json=answer_data,
        timeout=10
    )
    assert response.status_code == 200
    result = response.json()
    
    assert result["questionId"] == question_id
    assert result["studentAnswer"] == "test answer"
    assert "score" in result
    assert result["score"] in ["Full Marks", "Partial Marks", "Incorrect"]
    print(f"   ✓ Submitted answer - Score: {result['score']}")

def test_get_summary(run_id, session):
    """Test getting summary."""
    print("\n7. Testing get summary...")
    
    response = session.get(f"{BASE_URL}/api/runs/{run_id}/summary", timeout=10)
    assert response.status_code == 200
    summary = response.json()
    
    assert "revisionId" in summary
    assert "questions" in summary
    assert "overallAccuracy" in summary
    assert len(summary["questions"]) > 0
    print(f"   ✓ Got summary - Accuracy: {summary['overallAccuracy']}%, Questions: {len(summary['questions'])}")
    
    return summary

def test_database_persistence(revision_id, run_id):
    """Test that data is persisted in database."""
    print("\n8. Testing database persistence...")
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("   ⚠ DATABASE_URL not set - skipping database persistence test")
        return
    
    try:
        from my_revision_helper.database import get_db, engine
        from my_revision_helper.models_db import Revision, RevisionRun, RunQuestion, RunAnswer
        
        if not engine:
            print("   ⚠ Database engine not available - skipping")
            return
        
        db_gen = get_db()
        db = next(db_gen)
        
        if not db:
            print("   ⚠ Database session not available - skipping")
            return
        
        # Check revision
        revision = db.query(Revision).filter(Revision.id == revision_id).first()
        assert revision is not None, "Revision not found in database"
        print(f"   ✓ Revision {revision_id} found in database")
        
        # Check run
        run = db.query(RevisionRun).filter(RevisionRun.id == run_id).first()
        assert run is not None, "Run not found in database"
        print(f"   ✓ Run {run_id} found in database")
        
        # Check questions
        questions = db.query(RunQuestion).filter(RunQuestion.run_id == run_id).all()
        assert len(questions) > 0, "No questions found in database"
        print(f"   ✓ Found {len(questions)} question(s) in database")
        
        # Check answers
        answers = db.query(RunAnswer).filter(RunAnswer.run_id == run_id).all()
        assert len(answers) > 0, "No answers found in database"
        print(f"   ✓ Found {len(answers)} answer(s) in database")
        
        db_gen.close()
        
    except ImportError:
        print("   ⚠ Database modules not available - skipping")
    except Exception as e:
        print(f"   ✗ Database persistence test failed: {e}")
        raise

def main():
    """Run all E2E smoke tests."""
    print("=" * 60)
    print("End-to-End Smoke Test")
    print("=" * 60)
    print()
    
    try:
        test_health()
        revision_id, session, session_id = test_create_revision_anonymous()
        listed_revision_id = test_list_revisions(session)
        assert listed_revision_id == revision_id, "Revision ID mismatch"
        run_id = test_start_run(revision_id, session)
        question_id, question_text = test_get_question(run_id, session)
        test_submit_answer(run_id, question_id, session)
        summary = test_get_summary(run_id, session)
        test_database_persistence(revision_id, run_id)
        
        print("\n" + "=" * 60)
        print("✅ All E2E smoke tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

