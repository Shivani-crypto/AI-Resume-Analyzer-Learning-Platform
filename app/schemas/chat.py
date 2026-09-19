from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    lesson_id: Optional[int] = None # Optional: If the user is asking about a specific lesson
    skill: Optional[str] = None     # Optional: Target skill context for missing skills
    language: str = "English"       # Multilingual support

class ChatResponse(BaseModel):
    response: str
    source_documents: Optional[list] = []
