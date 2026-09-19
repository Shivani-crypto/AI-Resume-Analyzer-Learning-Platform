from fastapi import APIRouter, Depends, HTTPException
from ..schemas.quiz import QuizRequest, QuizResponse
from ..ai.quiz_generator import generate_quiz
from ..models.user import User
from .auth import get_current_user

router = APIRouter()

from sqlalchemy.orm import Session
from ..core.database import get_db
from ..services.quiz_service import QuizService

@router.post("/generate", response_model=QuizResponse)
def generate_ai_quiz(
    request: QuizRequest, 
    current_user: User = Depends(get_current_user)
):
    """
    Generates a personalized, AI-driven multiple choice quiz for a student.
    Uses the student's preferred language automatically.
    """
    lang = current_user.preferred_language or request.language or "English"
    try:
        return QuizService.generate_assessment_quiz(
            topic=request.topic,
            num_questions=request.num_questions,
            difficulty=request.difficulty,
            language=lang
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate AI Quiz. Please try again.")

from pydantic import BaseModel

class QuizSubmitRequest(BaseModel):
    topic: str
    score: int
    total_questions: int = 5

@router.post("/submit")
def submit_quiz(
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Records quiz submission, calculates XP, and saves to database."""
    return QuizService.record_quiz_score(
        user=current_user,
        topic=payload.topic,
        score=payload.score,
        total_questions=payload.total_questions,
        db=db
    )
