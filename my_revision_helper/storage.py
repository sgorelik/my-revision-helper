"""
Storage abstraction layer.

Routes data to database (for persistence) or in-memory storage based on authentication.
All data is persisted to database when available, but anonymous users can only
access their data within the current session.
"""

from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from .models_db import User, Revision, RevisionRun, RunQuestion, RunAnswer
import uuid
import logging

logger = logging.getLogger(__name__)


def get_or_create_user(db: Session, user_id: str, email: str, name: Optional[str] = None) -> User:
    """Get or create a user in the database."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, email=email, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user_id}")
    return user


class StorageAdapter:
    """
    Abstraction layer for storage - routes to DB or in-memory based on auth.
    
    Key behavior:
    - Authenticated users: Data stored with user_id, retrievable later
    - Anonymous users: Data stored with session_id, only accessible in current session
    - All data is persisted to database when available
    """
    
    def __init__(self, user: Optional[Dict[str, str]], db: Optional[Session] = None, session_id: Optional[str] = None):
        self.user = user
        self.db = db
        self.session_id = session_id or str(uuid.uuid4())  # Generate session ID if not provided
        self.is_authenticated = user is not None and db is not None
        self.use_database = db is not None
    
    def create_revision(self, revision_data: dict) -> dict:
        """Create revision in database (always persist when DB available)."""
        if self.use_database:
            return self._create_revision_db(revision_data)
        else:
            return self._create_revision_memory(revision_data)
    
    def _create_revision_db(self, revision_data: dict) -> dict:
        """Create revision in database."""
        revision = Revision(
            id=revision_data["id"],
            user_id=self.user["user_id"] if self.is_authenticated else None,
            session_id=self.session_id if not self.is_authenticated else None,
            name=revision_data["name"],
            subject=revision_data["subject"],
            topics=revision_data["topics"],
            description=revision_data.get("description"),
            desired_question_count=revision_data["desiredQuestionCount"],
            accuracy_threshold=revision_data["accuracyThreshold"],
            extracted_texts=revision_data.get("extractedTexts", {}),
            uploaded_files=revision_data.get("uploadedFiles"),
        )
        self.db.add(revision)
        self.db.commit()
        self.db.refresh(revision)
        
        logger.info(f"Created revision {revision.id} for {'user' if self.is_authenticated else 'session'} {self.user['user_id'] if self.is_authenticated else self.session_id}")
        
        return {
            "id": revision.id,
            "name": revision.name,
            "subject": revision.subject,
            "topics": revision.topics,
            "description": revision.description,
            "desiredQuestionCount": revision.desired_question_count,
            "accuracyThreshold": revision.accuracy_threshold,
            "uploadedFiles": revision.uploaded_files,
            "extractedTextPreview": revision_data.get("extractedTextPreview"),
        }
    
    def _create_revision_memory(self, revision_data: dict) -> dict:
        """Create revision in memory (fallback when DB not available)."""
        from .api import REVISION_DEFS
        revision_id = revision_data["id"]
        REVISION_DEFS[revision_id] = revision_data
        return revision_data
    
    def list_revisions(self) -> List[dict]:
        """List revisions - authenticated users see their revisions, anonymous see session revisions."""
        if self.use_database:
            return self._list_revisions_db()
        else:
            return self._list_revisions_memory()
    
    def _list_revisions_db(self) -> List[dict]:
        """List revisions from database."""
        if self.is_authenticated:
            # Authenticated: get by user_id
            revisions = self.db.query(Revision).filter(
                Revision.user_id == self.user["user_id"]
            ).all()
        else:
            # Anonymous: get by session_id (only current session)
            revisions = self.db.query(Revision).filter(
                Revision.session_id == self.session_id
            ).all()
        
        return [{
            "id": r.id,
            "name": r.name,
            "subject": r.subject,
            "topics": r.topics,
            "description": r.description,
            "desiredQuestionCount": r.desired_question_count,
            "accuracyThreshold": r.accuracy_threshold,
            "uploadedFiles": r.uploaded_files,
            "extractedTextPreview": None,
        } for r in revisions]
    
    def _list_revisions_memory(self) -> List[dict]:
        """List revisions from memory (fallback)."""
        from .api import REVISION_DEFS
        return list(REVISION_DEFS.values())
    
    def get_revision(self, revision_id: str) -> Optional[dict]:
        """Get revision - only if user owns it or it's in current session."""
        if self.use_database:
            return self._get_revision_db(revision_id)
        else:
            return self._get_revision_memory(revision_id)
    
    def _get_revision_db(self, revision_id: str) -> Optional[dict]:
        """Get revision from database with access control."""
        if self.is_authenticated:
            revision = self.db.query(Revision).filter(
                Revision.id == revision_id,
                Revision.user_id == self.user["user_id"]
            ).first()
        else:
            # Anonymous: only if it belongs to current session
            revision = self.db.query(Revision).filter(
                Revision.id == revision_id,
                Revision.session_id == self.session_id
            ).first()
        
        if not revision:
            return None
        
        return {
            "id": revision.id,
            "name": revision.name,
            "subject": revision.subject,
            "topics": revision.topics,
            "description": revision.description,
            "desiredQuestionCount": revision.desired_question_count,
            "accuracyThreshold": revision.accuracy_threshold,
            "extractedTexts": revision.extracted_texts or {},
            "uploadedFiles": revision.uploaded_files,
        }
    
    def _get_revision_memory(self, revision_id: str) -> Optional[dict]:
        """Get revision from memory (fallback)."""
        from .api import REVISION_DEFS
        return REVISION_DEFS.get(revision_id)
    
    def create_run(self, run_data: dict) -> dict:
        """Create run in database."""
        if self.use_database:
            return self._create_run_db(run_data)
        else:
            return self._create_run_memory(run_data)
    
    def _create_run_db(self, run_data: dict) -> dict:
        """Create run in database."""
        run = RevisionRun(
            id=run_data["id"],
            user_id=self.user["user_id"] if self.is_authenticated else None,
            session_id=self.session_id if not self.is_authenticated else None,
            revision_id=run_data["revisionId"],
            status=run_data.get("status", "running"),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        
        return {
            "id": run.id,
            "revisionId": run.revision_id,
            "status": run.status,
        }
    
    def _create_run_memory(self, run_data: dict) -> dict:
        """Create run in memory (fallback)."""
        from .api import REVISION_RUNS
        REVISION_RUNS[run_data["id"]] = run_data
        return run_data
    
    def get_run(self, run_id: str) -> Optional[dict]:
        """Get run with access control."""
        if self.use_database:
            return self._get_run_db(run_id)
        else:
            return self._get_run_memory(run_id)
    
    def _get_run_db(self, run_id: str) -> Optional[dict]:
        """Get run from database with access control."""
        if self.is_authenticated:
            run = self.db.query(RevisionRun).filter(
                RevisionRun.id == run_id,
                RevisionRun.user_id == self.user["user_id"]
            ).first()
        else:
            run = self.db.query(RevisionRun).filter(
                RevisionRun.id == run_id,
                RevisionRun.session_id == self.session_id
            ).first()
        
        if not run:
            return None
        
        return {
            "id": run.id,
            "revisionId": run.revision_id,
            "status": run.status,
        }
    
    def _get_run_memory(self, run_id: str) -> Optional[dict]:
        """Get run from memory (fallback)."""
        from .api import REVISION_RUNS
        return REVISION_RUNS.get(run_id)
    
    def store_questions(self, run_id: str, questions: List[dict]):
        """Store questions for a run."""
        if self.use_database:
            self._store_questions_db(run_id, questions)
        else:
            self._store_questions_memory(run_id, questions)
    
    def _store_questions_db(self, run_id: str, questions: List[dict]):
        """Store questions in database."""
        # Delete existing questions for this run
        self.db.query(RunQuestion).filter(RunQuestion.run_id == run_id).delete()
        
        # Add new questions
        for idx, q in enumerate(questions):
            question = RunQuestion(
                id=q["id"],
                run_id=run_id,
                question_text=q["text"],
                question_index=idx,
            )
            self.db.add(question)
        self.db.commit()
    
    def _store_questions_memory(self, run_id: str, questions: List[dict]):
        """Store questions in memory (fallback)."""
        from .api import RUN_QUESTIONS
        RUN_QUESTIONS[run_id] = questions
    
    def get_questions(self, run_id: str) -> List[dict]:
        """Get questions for a run."""
        if self.use_database:
            return self._get_questions_db(run_id)
        else:
            return self._get_questions_memory(run_id)
    
    def _get_questions_db(self, run_id: str) -> List[dict]:
        """Get questions from database."""
        questions = self.db.query(RunQuestion).filter(
            RunQuestion.run_id == run_id
        ).order_by(RunQuestion.question_index).all()
        
        return [{"id": q.id, "text": q.question_text} for q in questions]
    
    def _get_questions_memory(self, run_id: str) -> List[dict]:
        """Get questions from memory (fallback)."""
        from .api import RUN_QUESTIONS
        return RUN_QUESTIONS.get(run_id, [])
    
    def store_answer(self, run_id: str, answer_data: dict):
        """Store answer result."""
        if self.use_database:
            self._store_answer_db(run_id, answer_data)
        else:
            self._store_answer_memory(run_id, answer_data)
    
    def _store_answer_db(self, run_id: str, answer_data: dict):
        """Store answer in database."""
        answer = RunAnswer(
            id=str(uuid.uuid4()),
            run_id=run_id,
            question_id=answer_data["questionId"],
            student_answer=answer_data["studentAnswer"],
            is_correct=answer_data.get("isCorrect", False),
            score=answer_data.get("score", "Incorrect"),
            correct_answer=answer_data.get("correctAnswer", ""),
            explanation=answer_data.get("explanation"),
            error=answer_data.get("error"),
        )
        self.db.add(answer)
        self.db.commit()
    
    def _store_answer_memory(self, run_id: str, answer_data: dict):
        """Store answer in memory (fallback)."""
        from .api import RUN_ANSWERS
        if run_id not in RUN_ANSWERS:
            RUN_ANSWERS[run_id] = []
        RUN_ANSWERS[run_id].append(answer_data)
    
    def get_answers(self, run_id: str) -> List[dict]:
        """Get all answers for a run."""
        if self.use_database:
            return self._get_answers_db(run_id)
        else:
            return self._get_answers_memory(run_id)
    
    def _get_answers_db(self, run_id: str) -> List[dict]:
        """Get answers from database."""
        answers = self.db.query(RunAnswer).filter(
            RunAnswer.run_id == run_id
        ).order_by(RunAnswer.created_at).all()
        
        return [{
            "questionId": a.question_id,
            "questionText": a.question.question_text if a.question else None,
            "studentAnswer": a.student_answer,
            "isCorrect": a.is_correct,
            "score": a.score,
            "correctAnswer": a.correct_answer,
            "explanation": a.explanation,
            "error": a.error,
        } for a in answers]
    
    def _get_answers_memory(self, run_id: str) -> List[dict]:
        """Get answers from memory (fallback)."""
        from .api import RUN_ANSWERS
        return RUN_ANSWERS.get(run_id, [])

