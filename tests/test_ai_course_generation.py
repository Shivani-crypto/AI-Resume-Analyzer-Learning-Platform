try:
    import pytest
except ImportError:
    pytest = None

import json
from db import init_db, save_generated_course, get_generated_course
from utils.analyzer import validate_generated_course_content, generate_personalized_skill_course
from app.ai.tutor import generate_tutor_response
from app.schemas.chat import ChatRequest

if pytest:
    @pytest.fixture(autouse=True)
    def setup_database():
        init_db()
else:
    init_db()

def test_semantic_validation_valid_course():
    content = {
        "skill": "FastAPI",
        "title": "FastAPI Crash Course",
        "level": "Intermediate",
        "estimated_time": "5 minutes",
        "learning_objective": "Learn FastAPI async routes and Pydantic validation.",
        "why_this_skill_matters": "FastAPI enables high throughput web APIs in modern Python microservices.",
        "one_minute_demo": [
            {"scene": 1, "title": "Intro", "narration": "FastAPI overview", "bullets": ["A1"], "code": "from fastapi import FastAPI"},
            {"scene": 2, "title": "App", "narration": "App init", "bullets": ["A2"], "code": "app = FastAPI()"},
            {"scene": 3, "title": "Route", "narration": "Endpoint definition", "bullets": ["A3"], "code": "@app.get('/')\nasync def root(): return {'msg': 'ok'}"},
            {"scene": 4, "title": "Run", "narration": "Uvicorn server", "bullets": ["A4"], "code": "import uvicorn\nuvicorn.run(app)"}
        ],
        "slides": [
            {"title": "1. FastAPI Fundamentals", "bullets": ["b1"], "code": "code1", "explanation_script": "script1"},
            {"title": "2. Async Routes & Uvicorn", "bullets": ["b2"], "code": "code2", "explanation_script": "script2"},
            {"title": "3. Pydantic Schemas", "bullets": ["b3"], "code": "code3", "explanation_script": "script3"},
            {"title": "4. Security & CORS", "bullets": ["b4"], "code": "code4", "explanation_script": "script4"}
        ],
        "core_concepts": [
            {"title": "Pillar 1", "icon": "fa-cube", "color": "#6366f1", "desc": "Desc 1"},
            {"title": "Pillar 2", "icon": "fa-database", "color": "#10b981", "desc": "Desc 2"},
            {"title": "Pillar 3", "icon": "fa-bolt", "color": "#f59e0b", "desc": "Desc 3"},
            {"title": "Pillar 4", "icon": "fa-shield", "color": "#ec4899", "desc": "Desc 4"}
        ],
        "code_example": {
            "filename": "main.py",
            "language": "python",
            "code": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): return {'status': 'healthy'}",
            "explanation": ["Explanation line"]
        },
        "real_world_use_case": "Production microservice API behind Uvicorn and Nginx.",
        "common_mistakes": ["Blocking I/O in async endpoints"],
        "quick_recap": ["FastAPI uses Pydantic and Starlette."],
        "quiz_topics": [
            {
                "question": "What ASGI server commonly serves FastAPI applications?",
                "options": [{"id": "a", "text": "Uvicorn"}, {"id": "b", "text": "Apache"}],
                "correct_option_id": "a",
                "explanation": "Uvicorn is a lightning-fast ASGI server."
            }
        ]
    }
    
    is_valid, reason = validate_generated_course_content("FastAPI", content)
    assert is_valid is True, f"Expected valid course, got error: {reason}"

def test_semantic_validation_rejects_offtopic_course():
    offtopic_content = {
        "skill": "FastAPI",
        "title": "FastAPI Crash Course",
        "one_minute_demo": [
            {"scene": 1, "narration": "Express setup", "code": "const express = require('express');"},
            {"scene": 2, "narration": "App listen", "code": "const app = express(); app.listen(3000);"},
            {"scene": 3, "narration": "Routes", "code": "app.get('/', (req, res) => res.send('OK'));"},
            {"scene": 4, "narration": "Middleware", "code": "app.use(express.json());"}
        ],
        "slides": [{"title": "1", "bullets": ["b"]} for _ in range(4)],
        "core_concepts": [{"title": "p", "icon": "i", "color": "c", "desc": "d"} for _ in range(4)],
        "code_example": {"code": "const express = require('express'); app.listen(3000);"},
        "common_mistakes": ["m"],
        "quick_recap": ["r"],
        "quiz_topics": [{"question": "q"}]
    }
    
    is_valid, reason = validate_generated_course_content("FastAPI", offtopic_content)
    assert is_valid is False
    assert "FastAPI course generated Node/Express code" in reason or "lacks specific technical concepts" in reason

def test_db_save_and_retrieve_generated_course():
    user_email = "test_ai_course_user@example.com"
    skill = "Docker"
    content_data = {"skill": "Docker", "title": "Docker Containerization Masterclass"}
    content_json = json.dumps(content_data)

    course_id = save_generated_course(user_email=user_email, skill=skill, content_json=content_json, title="Docker Masterclass")
    assert course_id is not None

    retrieved = get_generated_course(user_email, skill)
    assert retrieved is not None
    assert retrieved["skill"] == skill
    assert json.loads(retrieved["content_json"])["title"] == "Docker Containerization Masterclass"

def test_ai_tutor_response_with_skill_context():
    req = ChatRequest(
        message="What is the main benefit of async def routes?",
        skill="FastAPI",
        language="English"
    )
    res = generate_tutor_response(req)
    assert res is not None
    assert res.response is not None
    assert len(res.response) > 0

def test_multiple_skills_validation():
    skills_and_samples = {
        "Python": {
            "skill": "Python",
            "title": "Python Programming",
            "level": "Beginner",
            "one_minute_demo": [{"scene": i, "narration": f"Python part {i}", "code": f"# Python demo {i}\ndef greet(): return 'hello'"} for i in range(1, 5)],
            "slides": [{"title": f"Slide {i}", "bullets": ["b"], "explanation_script": "s"} for i in range(1, 5)],
            "core_concepts": [{"title": f"Concept {i}", "desc": "d", "icon": "fa-code", "color": "#6366f1"} for i in range(1, 5)],
            "code_example": {"code": "def process_data(items):\n    return [x * 2 for x in items]", "language": "python"},
            "common_mistakes": ["Mutable default arguments"],
            "quick_recap": ["Python uses indentation."],
            "quiz_topics": [{"question": "What is Python?", "options": [{"id": "a", "text": "Language"}], "correct_option_id": "a", "explanation": "Python is a language."}]
        },
        "Docker": {
            "skill": "Docker",
            "title": "Docker Containers",
            "level": "Intermediate",
            "one_minute_demo": [{"scene": i, "narration": f"Docker scene {i}", "code": f"FROM python:3.10-slim\nWORKDIR /app\nRUN echo 'scene {i}'"} for i in range(1, 5)],
            "slides": [{"title": f"Docker {i}", "bullets": ["b"], "explanation_script": "s"} for i in range(1, 5)],
            "core_concepts": [{"title": f"Docker {i}", "desc": "d", "icon": "fa-box", "color": "#10b981"} for i in range(1, 5)],
            "code_example": {"code": "FROM python:3.10\nCOPY . /app\nCMD ['python', 'app.py']", "language": "dockerfile"},
            "common_mistakes": ["Running containers as root"],
            "quick_recap": ["Docker uses images and containers."],
            "quiz_topics": [{"question": "What is a Dockerfile?", "options": [{"id": "a", "text": "Blueprint"}], "correct_option_id": "a", "explanation": "A Dockerfile builds images."}]
        }
    }

    for skill, content in skills_and_samples.items():
        is_valid, reason = validate_generated_course_content(skill, content)
        assert is_valid is True, f"Failed for {skill}: {reason}"

if __name__ == "__main__":
    init_db()
    print("[RUNNING] test_semantic_validation_valid_course...")
    test_semantic_validation_valid_course()
    print("[PASS] test_semantic_validation_valid_course")

    print("[RUNNING] test_semantic_validation_rejects_offtopic_course...")
    test_semantic_validation_rejects_offtopic_course()
    print("[PASS] test_semantic_validation_rejects_offtopic_course")

    print("[RUNNING] test_db_save_and_retrieve_generated_course...")
    test_db_save_and_retrieve_generated_course()
    print("[PASS] test_db_save_and_retrieve_generated_course")

    print("[RUNNING] test_multiple_skills_validation...")
    test_multiple_skills_validation()
    print("[PASS] test_multiple_skills_validation")

    print("[RUNNING] test_ai_tutor_response_with_skill_context...")
    test_ai_tutor_response_with_skill_context()
    print("[PASS] test_ai_tutor_response_with_skill_context")

    print("\nALL AI COURSE GENERATION TESTS PASSED SUCCESSFULLY!")

