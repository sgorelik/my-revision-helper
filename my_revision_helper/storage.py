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


def get_or_create_user(db: Session, user_id: str, email: Optional[str] = None, name: Optional[str] = None) -> User:
    """Get or create a user in the database."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # Email is required by database, use a fallback if not provided
        # Use user_id as email if email is None (some auth providers might not include email)
        user_email = email or f"{user_id}@auth0.local"
        user = User(id=user_id, email=user_email, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user_id} with email: {user_email}")
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
        
        # In-memory storage (fallback when DB not available)
        if not self.use_database:
            from .api import REVISION_DEFS, REVISION_RUNS, RUN_QUESTIONS, RUN_ANSWERS
            self._revisions = REVISION_DEFS
            self._runs = REVISION_RUNS
            self._questions = RUN_QUESTIONS
            self._answers = RUN_ANSWERS
    
    def _get_user_id(self) -> Optional[str]:
        """Get user_id if authenticated, None otherwise."""
        return self.user["user_id"] if self.is_authenticated else None
    
    def _get_session_id(self) -> Optional[str]:
        """Get session_id if not authenticated, None otherwise."""
        return self.session_id if not self.is_authenticated else None
    
    def _ensure_user_exists(self):
        """Ensure user exists in database if authenticated."""
        if self.is_authenticated and self.use_database:
            get_or_create_user(
                self.db,
                self.user["user_id"],
                self.user.get("email"),
                self.user.get("name")
            )
    
    def create_revision(self, revision_data: dict) -> dict:
        """Create revision - persists to database if available, otherwise in-memory."""
        self._ensure_user_exists()
        
        user_id = self._get_user_id()
        session_id = self._get_session_id()
        
        logger.info(f"Creating revision: is_authenticated={self.is_authenticated}, user_id={user_id}, session_id={session_id}")
        
        if self.use_database:
            revision = Revision(
                id=revision_data["id"],
                user_id=user_id,
                session_id=session_id,
                name=revision_data["name"],
                subject=revision_data["subject"],
                topics=revision_data["topics"],
                description=revision_data.get("description"),
                desired_question_count=revision_data["desiredQuestionCount"],
                accuracy_threshold=revision_data["accuracyThreshold"],
                question_style=revision_data.get("questionStyle", "free-text"),
                extracted_texts=revision_data.get("extractedTexts", {}),
                uploaded_files=revision_data.get("uploadedFiles"),
            )
            self.db.add(revision)
            self.db.commit()
            self.db.refresh(revision)
            
            result = {
                "id": revision.id,
                "name": revision.name,
                "subject": revision.subject,
                "topics": revision.topics,
                "description": revision.description,
                "desiredQuestionCount": revision.desired_question_count,
                "accuracyThreshold": revision.accuracy_threshold,
                "questionStyle": revision.question_style,
                "uploadedFiles": revision.uploaded_files,
                "extractedTextPreview": revision_data.get("extractedTextPreview"),
            }
        else:
            # In-memory storage - add session_id/user_id for filtering
            revision_data_with_meta = revision_data.copy()
            if user_id:
                revision_data_with_meta["userId"] = user_id
            if session_id:
                revision_data_with_meta["sessionId"] = session_id
            self._revisions[revision_data["id"]] = revision_data_with_meta
            result = revision_data_with_meta
        
        logger.info(f"Created revision {revision_data['id']} for {'user' if self.is_authenticated else 'session'} {user_id or session_id}")
        return result
    
    def list_revisions(self) -> List[dict]:
        """List revisions - authenticated users see their revisions, anonymous see session revisions."""
        if self.use_database:
            if self.is_authenticated:
                revisions = self.db.query(Revision).filter(
                    Revision.user_id == self.user["user_id"]
                ).all()
                logger.info(f"Listing revisions for authenticated user {self.user['user_id']}: found {len(revisions)} revisions")
            else:
                revisions = self.db.query(Revision).filter(
                    Revision.session_id == self.session_id
                ).all()
                logger.info(f"Found {len(revisions)} revisions for session {self.session_id}")
            
            return [{
                "id": r.id,
                "name": r.name,
                "subject": r.subject,
                "topics": r.topics,
                "description": r.description,
                "desiredQuestionCount": r.desired_question_count,
                "accuracyThreshold": r.accuracy_threshold,
                "questionStyle": r.question_style,
                "uploadedFiles": r.uploaded_files,
                "extractedTextPreview": None,
            } for r in revisions]
        else:
            # In-memory: filter by user_id or session_id
            if self.is_authenticated:
                # For authenticated users, only return revisions with matching user_id
                user_id = self._get_user_id()
                return [
                    r for r in self._revisions.values()
                    if r.get("userId") == user_id
                ]
            else:
                # For anonymous users, only return revisions with matching session_id
                session_id = self._get_session_id()
                return [
                    r for r in self._revisions.values()
                    if r.get("sessionId") == session_id
                ]
    
    def get_revision(self, revision_id: str) -> Optional[dict]:
        """Get revision - only if user owns it or it's in current session."""
        if self.use_database:
            if self.is_authenticated:
                revision = self.db.query(Revision).filter(
                    Revision.id == revision_id,
                    Revision.user_id == self.user["user_id"]
                ).first()
            else:
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
                "questionStyle": revision.question_style,
                "extractedTexts": revision.extracted_texts or {},
                "uploadedFiles": revision.uploaded_files,
            }
        else:
            # In-memory storage - check access control
            revision = self._revisions.get(revision_id)
            if not revision:
                return None
            
            # Verify user/session has access
            if self.is_authenticated:
                user_id = self._get_user_id()
                if revision.get("userId") != user_id:
                    return None
            else:
                session_id = self._get_session_id()
                if revision.get("sessionId") != session_id:
                    return None
            
            return revision
    
    def delete_revision(self, revision_id: str) -> bool:
        """Delete revision - only if user owns it or it's in current session."""
        try:
            if self.use_database:
                if self.is_authenticated:
                    revision = self.db.query(Revision).filter(
                        Revision.id == revision_id,
                        Revision.user_id == self.user["user_id"]
                    ).first()
                else:
                    # Non-authenticated users cannot delete revisions
                    logger.warning(f"Non-authenticated user attempted to delete revision {revision_id}")
                    return False
                
                if not revision:
                    logger.warning(f"Revision {revision_id} not found or user doesn't have access")
                    return False
                
                # Delete the revision (cascade will handle related runs, questions, answers)
                self.db.delete(revision)
                self.db.commit()
                logger.info(f"Deleted revision {revision_id} for user {self.user['user_id']}")
                return True
            else:
                # In-memory storage - check access control
                revision = self._revisions.get(revision_id)
                if not revision:
                    return False
                
                # Only authenticated users can delete
                if not self.is_authenticated:
                    logger.warning(f"Non-authenticated user attempted to delete revision {revision_id}")
                    return False
                
                # Verify user owns this revision
                user_id = self._get_user_id()
                if revision.get("userId") != user_id:
                    logger.warning(f"User {user_id} attempted to delete revision {revision_id} owned by {revision.get('userId')}")
                    return False
                
                # Delete from in-memory storage
                del self._revisions[revision_id]
                logger.info(f"Deleted revision {revision_id} from in-memory storage")
                return True
        except Exception as e:
            logger.error(f"Failed to delete revision {revision_id}: {e}")
            if self.use_database:
                self.db.rollback()
            return False
    
    def create_run(self, run_data: dict) -> dict:
        """Create run - persists to database if available, otherwise in-memory."""
        try:
            self._ensure_user_exists()
            
            user_id = self._get_user_id()
            session_id = self._get_session_id()
            
            logger.info(f"Creating run: is_authenticated={self.is_authenticated}, user_id={user_id}, session_id={session_id}, revision_id={run_data['revisionId']}")
            
            if self.use_database:
                run = RevisionRun(
                    id=run_data["id"],
                    user_id=user_id,
                    session_id=session_id,
                    revision_id=run_data["revisionId"],
                    status=run_data.get("status", "running"),
                )
                self.db.add(run)
                self.db.commit()
                self.db.refresh(run)
                
                result = {
                    "id": run.id,
                    "revisionId": run.revision_id,
                    "status": run.status,
                }
                logger.info(f"Created run {run.id} successfully")
            else:
                # In-memory storage - add session_id/user_id for filtering
                run_data_with_meta = run_data.copy()
                if user_id:
                    run_data_with_meta["userId"] = user_id
                if session_id:
                    run_data_with_meta["sessionId"] = session_id
                self._runs[run_data["id"]] = run_data_with_meta
                result = run_data_with_meta
            
            return result
        except Exception as e:
            logger.error(f"Failed to create run: {e}")
            if self.use_database:
                self.db.rollback()
            raise
    
    def get_run(self, run_id: str) -> Optional[dict]:
        """Get run with access control."""
        if self.use_database:
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
        else:
            # In-memory storage - check access control
            run = self._runs.get(run_id)
            if not run:
                return None
            
            # Verify user/session has access
            if self.is_authenticated:
                user_id = self._get_user_id()
                if run.get("userId") != user_id:
                    return None
            else:
                session_id = self._get_session_id()
                if run.get("sessionId") != session_id:
                    return None
            
            return run
    
    def store_questions(self, run_id: str, questions: List[dict]):
        """Store questions for a run."""
        try:
            if self.use_database:
                # Delete existing questions for this run
                self.db.query(RunQuestion).filter(RunQuestion.run_id == run_id).delete()
                
                # Add new questions
                for idx, q in enumerate(questions):
                    question = RunQuestion(
                        id=q["id"],
                        run_id=run_id,
                        question_text=q["text"],
                        question_index=idx,
                        question_style=q.get("questionStyle"),
                        options=q.get("options"),
                        correct_answer_index=q.get("correctAnswerIndex"),
                        rationale=q.get("rationale"),
                    )
                    self.db.add(question)
                self.db.commit()
                logger.info(f"Stored {len(questions)} questions for run {run_id}")
            else:
                # In-memory storage
                self._questions[run_id] = questions
        except Exception as e:
            logger.error(f"Failed to store questions for run {run_id}: {e}")
            if self.use_database:
                self.db.rollback()
            raise
    
    def get_questions(self, run_id: str) -> List[dict]:
        """Get questions for a run."""
        if self.use_database:
            questions = self.db.query(RunQuestion).filter(
                RunQuestion.run_id == run_id
            ).order_by(RunQuestion.question_index).all()
            
            result = []
            for q in questions:
                question_dict = {
                    "id": q.id,
                    "text": q.question_text,
                }
                # Include multiple choice fields if present
                if q.question_style:
                    question_dict["questionStyle"] = q.question_style
                if q.options:
                    question_dict["options"] = q.options
                if q.correct_answer_index is not None:
                    question_dict["correctAnswerIndex"] = q.correct_answer_index
                if q.rationale:
                    question_dict["rationale"] = q.rationale
                result.append(question_dict)
            return result
        else:
            # In-memory storage
            return self._questions.get(run_id, [])
    
    def store_answer(self, run_id: str, answer_data: dict):
        """Store answer result."""
        if self.use_database:
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
        else:
            # In-memory storage
            if run_id not in self._answers:
                self._answers[run_id] = []
            self._answers[run_id].append(answer_data)
    
    def get_answers(self, run_id: str) -> List[dict]:
        """Get all answers for a run."""
        if self.use_database:
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
        else:
            # In-memory storage
            return self._answers.get(run_id, [])
    
    def list_completed_runs(self) -> List[dict]:
        """List all completed runs with revision info and summary data."""
        if self.use_database:
            # Get all runs for this user/session
            if self.is_authenticated:
                runs = self.db.query(RevisionRun).filter(
                    RevisionRun.user_id == self.user["user_id"]
                ).order_by(RevisionRun.created_at.desc()).all()
            else:
                runs = self.db.query(RevisionRun).filter(
                    RevisionRun.session_id == self.session_id
                ).order_by(RevisionRun.created_at.desc()).all()
            
            completed_runs = []
            for run in runs:
                # Check if run has answers (completed)
                answers = self.db.query(RunAnswer).filter(
                    RunAnswer.run_id == run.id
                ).all()
                
                if answers:
                    # Get revision info
                    revision = self.db.query(Revision).filter(
                        Revision.id == run.revision_id
                    ).first()
                    
                    if revision:
                        # Calculate score
                        total_score = 0.0
                        for a in answers:
                            if a.score == "Full Marks":
                                total_score += 100.0
                            elif a.score == "Partial Marks":
                                total_score += 50.0
                        accuracy = total_score / len(answers) if answers else 0.0
                        
                        completed_runs.append({
                            "runId": run.id,
                            "revisionId": revision.id,
                            "revisionName": revision.name,
                            "subject": revision.subject,
                            "completedAt": run.created_at.isoformat(),
                            "score": accuracy,
                            "totalQuestions": len(answers),
                            "threshold": revision.accuracy_threshold,
                        })
            
            return completed_runs
        else:
            # In-memory storage - filter by user_id or session_id, then check which runs have answers
            user_id = self._get_user_id()
            session_id = self._get_session_id()
            
            completed_runs = []
            for run_id, run_data in self._runs.items():
                # Filter by user_id or session_id
                if self.is_authenticated:
                    if run_data.get("userId") != user_id:
                        continue
                else:
                    if run_data.get("sessionId") != session_id:
                        continue
                
                answers = self._answers.get(run_id, [])
                if answers:
                    revision_id = run_data.get("revisionId")
                    revision = self._revisions.get(revision_id) if revision_id else None
                    
                    if revision:
                        # Calculate score
                        total_score = 0.0
                        for a in answers:
                            score = a.get("score", "Incorrect")
                            if score == "Full Marks":
                                total_score += 100.0
                            elif score == "Partial Marks":
                                total_score += 50.0
                        accuracy = total_score / len(answers) if answers else 0.0
                        
                        completed_runs.append({
                            "runId": run_id,
                            "revisionId": revision_id,
                            "revisionName": revision.get("name", "Unknown"),
                            "subject": revision.get("subject", "Unknown"),
                            "completedAt": run_data.get("createdAt", ""),
                            "score": accuracy,
                            "totalQuestions": len(answers),
                            "threshold": revision.get("accuracyThreshold", 80),
                        })
            
            return completed_runs
