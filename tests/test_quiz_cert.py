import pytest
from app.ai.quiz_generator import generate_quiz
from app.schemas.quiz import QuizRequest

def test_quiz_generation_schema():
    req = QuizRequest(topic="Python", num_questions=3, difficulty="Intermediate", language="English")
    quiz = generate_quiz(req)
    
    assert quiz.topic.lower() == "python"
    assert len(quiz.questions) > 0
    for q in quiz.questions:
        assert q.question
        assert len(q.options) >= 2
        assert q.correct_option_id in ["a", "b", "c", "d"]
