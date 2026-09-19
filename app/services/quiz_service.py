"""
Assessment and Quiz Service.
Generates skill-based assessments, evaluates student submissions,
updates XP and mastery points, and tracks QuizResult persistence.
"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.schemas.quiz import QuizRequest, QuizResponse
from app.ai.quiz_generator import generate_quiz
from app.models.analysis import QuizResult, SystemLog
from app.models.user import User

class QuizService:
    @staticmethod
    def generate_assessment_quiz(
        topic: str,
        num_questions: int = 5,
        difficulty: str = "Intermediate",
        language: str = "English"
    ) -> QuizResponse:
        """Generates a dynamic technical assessment for the given topic/skill."""
        req = QuizRequest(
            topic=topic.strip(),
            num_questions=max(1, min(10, num_questions)),
            difficulty=difficulty,
            language=language
        )
        return generate_quiz(req)

    @staticmethod
    def record_quiz_score(
        user: User,
        topic: str,
        score: int,
        total_questions: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Calculates score percentage, determines passing status,
        persists QuizResult, and awards XP.
        """
        clean_email = user.email.strip().lower() if user and user.email else "student@example.com"
        clean_topic = topic.strip().title()

        total = max(1, total_questions)
        score_pct = int((score / total) * 100) if score <= total else int(score)
        score_pct = min(100, max(0, score_pct))
        passed = score_pct >= 25

        # Save to database
        record = QuizResult(
            user_email=clean_email,
            user_id=user.id if user else None,
            topic=clean_topic,
            score=score,
            total_questions=total,
            passed=passed
        )
        db.add(record)

        log = SystemLog(
            user_email=clean_email,
            action=f"Completed Quiz on {clean_topic}: {score}/{total} ({score_pct}%)"
        )
        db.add(log)
        db.commit()
        db.refresh(record)

        xp_earned = score_pct * 25

        return {
            "id": record.id,
            "topic": clean_topic,
            "score": score_pct,
            "raw_score": score,
            "total_questions": total,
            "passed": passed,
            "xp_earned": xp_earned
        }

    @staticmethod
    def has_participated_or_passed(user_email: str, topic: str, db: Session) -> bool:
        """Checks if a student has previously attempted the quiz for a given topic."""
        if not user_email:
            return False
        clean_email = user_email.strip().lower()
        clean_topic = topic.strip().lower()
        found = db.query(QuizResult).filter(
            QuizResult.user_email == clean_email,
            QuizResult.topic.ilike(f"%{clean_topic}%")
        ).first()
        return found is not None
