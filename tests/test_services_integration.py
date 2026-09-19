import pytest
import os
import io
from fastapi import UploadFile
from app.core.database import SessionLocal, engine
from app.models.base import Base
from app.models.user import User
from app.models.progress import Certificate
from app.schemas.chat import ChatRequest
from app.services.resume_service import ResumeService, ALLOWED_RESUME_EXTENSIONS
from app.services.analysis_service import AnalysisService
from app.services.quiz_service import QuizService
from app.services.certificate_service import CertificateService
from app.services.progress_service import ProgressService
from app.services.tutor_service import TutorService
from app.services.ai_course_service import AICourseService

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    # Create or retrieve test user
    test_user = session.query(User).filter(User.email == "test_service_user@example.com").first()
    if not test_user:
        test_user = User(
            email="test_service_user@example.com",
            full_name="Service Test User",
            hashed_password="mock_hash",
            is_active=True
        )
        session.add(test_user)
        session.commit()
        session.refresh(test_user)
    yield session, test_user
    session.close()

def test_resume_service_extensions():
    assert ".pdf" in ALLOWED_RESUME_EXTENSIONS
    assert ".docx" in ALLOWED_RESUME_EXTENSIONS
    assert ".exe" not in ALLOWED_RESUME_EXTENSIONS

def test_resume_service_process(db_session):
    session, test_user = db_session
    # Generate genuine PDF stream using ReportLab
    from reportlab.pdfgen import canvas
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer)
    c.drawString(100, 750, "Candidate Resume with Python, FastAPI, and Docker experience.")
    c.save()
    pdf_buffer.seek(0)
    
    upload_file = UploadFile(filename="test_resume.pdf", file=pdf_buffer)
    
    filename, text, url = ResumeService.process_and_save_resume(upload_file, test_user, session)
    assert filename.startswith("user_")
    assert filename.endswith(".pdf")
    assert len(text) > 0

def test_analysis_service_scoring_and_run(db_session):
    session, test_user = db_session
    resume_text = "Proficient Python developer with FastAPI and SQL experience."
    job_text = "Looking for a Python developer with FastAPI, Docker, and AWS experience."
    
    score = AnalysisService.calculate_ml_match(resume_text, job_text)
    assert score > 0.0
    
    links = AnalysisService.get_job_links(["python", "fastapi"])
    assert "LinkedIn" in links
    assert "Indeed" in links
    
    result = AnalysisService.run_full_analysis(resume_text, job_text, test_user, session)
    assert "score" in result
    assert "missing_skills" in result
    assert any("Docker" in s or "Aws" in s or "AWS" in s for s in result["missing_skills"])

def test_quiz_service_flow(db_session):
    session, test_user = db_session
    quiz = QuizService.generate_assessment_quiz("Docker", num_questions=3)
    assert len(quiz.questions) == 3
    
    record = QuizService.record_quiz_score(
        user=test_user,
        topic="Docker",
        score=3,
        total_questions=3,
        db=session
    )
    assert record["passed"] is True
    assert record["score"] == 100
    assert record["xp_earned"] == 2500
    
    has_attempted = QuizService.has_participated_or_passed(test_user.email, "Docker", session)
    assert has_attempted is True

def test_certificate_service_generation_and_retrieval(db_session):
    session, test_user = db_session
    test_pdf = os.path.join("certificates", "test_cert.pdf")
    CertificateService.generate_pdf(test_user.full_name, "Docker Mastery", test_pdf)
    assert os.path.exists(test_pdf)
    
    cert = CertificateService.issue_ai_skill_certificate(
        skill="Docker",
        user=test_user,
        db=session,
        score=95
    )
    assert cert.id is not None
    assert "Docker" in cert.title
    assert cert.score == 95
    
    certs = CertificateService.get_user_certificates(test_user.email, session)
    assert len(certs) >= 1
    assert any(c["title"] == cert.title for c in certs)

def test_progress_service_history_aggregation(db_session):
    session, test_user = db_session
    history = ProgressService.get_user_history_data(test_user, session)
    assert "analyses" in history
    assert "certificates" in history
    assert "quiz_results" in history
    assert "mastery_points" in history
    assert history["mastery_points"] > 0

def test_tutor_service_query():
    chat_req = ChatRequest(message="What is a container?", skill="Docker", language="English")
    response = TutorService.answer_student_question(chat_req)
    assert response.response
    assert len(response.response) > 5
