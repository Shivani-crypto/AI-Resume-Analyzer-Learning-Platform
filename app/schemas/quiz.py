from pydantic import BaseModel
from typing import List, Optional

class QuizRequest(BaseModel):
    topic: str
    difficulty: str = "Beginner"
    language: str = "English"
    num_questions: int = 5
    lesson_id: Optional[int] = None # Optional: If the quiz should be based strictly on specific lesson notes

class QuizOption(BaseModel):
    id: str
    text: str

class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_option_id: str
    explanation: str

class QuizResponse(BaseModel):
    topic: str
    questions: List[QuizQuestion]
