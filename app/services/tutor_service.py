"""
AI Tutor and Doubt Resolution Service.
Coordinates RAG context retrieval and LLM completion for lesson-specific
and skill-specific student questions.
"""
from typing import Optional, Dict, Any
from app.schemas.chat import ChatRequest, ChatResponse
from app.ai.tutor import generate_tutor_response
from app.models.user import User

class TutorService:
    @staticmethod
    def answer_student_question(
        request: ChatRequest,
        user: Optional[User] = None
    ) -> ChatResponse:
        """
        Dispatches student question to the RAG tutor engine, ensuring
        preferred language and skill context are preserved.
        """
        if user and user.preferred_language:
            request.language = user.preferred_language

        return generate_tutor_response(request)
