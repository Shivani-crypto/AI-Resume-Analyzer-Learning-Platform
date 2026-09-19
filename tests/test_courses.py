import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.course import Course, Category, Module, Lesson

client = TestClient(app)

def test_get_published_courses():
    response = client.get("/api/courses/courses")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_course_detail():
    db = SessionLocal()
    course = db.query(Course).first()
    db.close()
    
    if course:
        response = client.get(f"/api/courses/courses/{course.id}")
        assert response.status_code == 200
        assert response.json()["id"] == course.id
