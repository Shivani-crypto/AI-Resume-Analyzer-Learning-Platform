from typing import Optional
from fastapi import APIRouter, Depends
from ..schemas.chat import ChatRequest, ChatResponse
from ..ai.tutor import generate_tutor_response
from ..models.user import User
from .auth import get_current_user, get_current_user_optional

from ..services.tutor_service import TutorService

router = APIRouter()

@router.post("/ask", response_model=ChatResponse)
def ask_tutor(
    request: ChatRequest, 
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Allows a student to ask the Multilingual AI Tutor a question, with optional user context.
    """
    return TutorService.answer_student_question(request, current_user)
