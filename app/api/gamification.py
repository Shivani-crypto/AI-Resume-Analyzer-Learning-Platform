import os
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.user import User
from ..models.course import Lesson, Course, Module
from ..models.progress import StudentProgress, Certificate, Badge
from ..models.analysis import QuizResult
from ..schemas.progress import ProgressUpdate, ProgressResponse, CertificateResponse, BadgeResponse
from .auth import get_current_user

from db import save_certificate, save_quiz_result

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

router = APIRouter()

def generate_pdf_certificate(user_name, course_name, filename):
    user_display = user_name or "Valued Scholar"
    course_display = course_name or "AI Mastery Course"
    
    if HAS_REPORTLAB:
        try:
            c = canvas.Canvas(filename, pagesize=landscape(letter))
            c.setStrokeColor(colors.HexColor("#6366f1"))
            c.setLineWidth(4)
            c.rect(0.5*inch, 0.5*inch, 10*inch, 7.5*inch)
            
            c.setStrokeColor(colors.HexColor("#e0e7ff"))
            c.setLineWidth(1.5)
            c.rect(0.6*inch, 0.6*inch, 9.8*inch, 7.3*inch)
            
            c.setFont("Helvetica-Bold", 32)
            c.setFillColor(colors.HexColor("#1e1b4b"))
            c.drawCentredString(5.5*inch, 6.6*inch, "TRUPROJECTS ACADEMY")
            
            c.setFont("Helvetica-Bold", 22)
            c.setFillColor(colors.HexColor("#4f46e5"))
            c.drawCentredString(5.5*inch, 5.9*inch, "CERTIFICATE OF ACHIEVEMENT")
            
            c.setFont("Helvetica", 15)
            c.setFillColor(colors.HexColor("#64748b"))
            c.drawCentredString(5.5*inch, 5.1*inch, "This certifies that")
            
            c.setFont("Helvetica-Bold", 26)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawCentredString(5.5*inch, 4.4*inch, str(user_display))
            
            c.setFont("Helvetica", 15)
            c.setFillColor(colors.HexColor("#64748b"))
            c.drawCentredString(5.5*inch, 3.7*inch, "has successfully demonstrated proficiency and completed:")
            
            c.setFont("Helvetica-Bold", 22)
            c.setFillColor(colors.HexColor("#4338ca"))
            c.drawCentredString(5.5*inch, 3.0*inch, str(course_display))
            
            c.setFont("Helvetica", 13)
            c.setFillColor(colors.HexColor("#94a3b8"))
            c.drawCentredString(5.5*inch, 1.8*inch, f"Issued by TruProjects Certification Authority • Verified Online")
            c.save()
            return
        except Exception as e:
            print(f"ReportLab generation exception: {e}")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Certificate of Achievement - {user_display}</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f1f5f9; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
  .cert-container {{ background: #ffffff; width: 900px; height: 620px; padding: 50px; border: 12px solid #4f46e5; outline: 3px solid #e0e7ff; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); text-align: center; position: relative; box-sizing: border-box; border-radius: 8px; }}
  .cert-header {{ font-size: 28px; font-weight: 800; color: #1e1b4b; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 5px; }}
  .cert-badge {{ font-size: 16px; color: #6366f1; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 30px; }}
  .cert-body {{ font-size: 18px; color: #64748b; margin: 15px 0 5px 0; }}
  .cert-name {{ font-size: 38px; font-weight: 800; color: #0f172a; margin: 15px 0; border-bottom: 2px solid #cbd5e1; display: inline-block; padding: 0 40px 10px 40px; }}
  .cert-course {{ font-size: 26px; font-weight: 700; color: #4338ca; margin: 15px 0; }}
  .cert-footer {{ position: absolute; bottom: 40px; left: 60px; right: 60px; display: flex; justify-content: space-between; align-items: flex-end; }}
  .signature-box {{ text-align: center; }}
  .signature-line {{ width: 180px; height: 2px; background: #94a3b8; margin-bottom: 8px; }}
  .btn-print {{ position: fixed; top: 20px; right: 20px; background: #4f46e5; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
  @media print {{ .btn-print {{ display: none; }} body {{ background: white; padding: 0; }} .cert-container {{ box-shadow: none; border-width: 8px; }} }}
</style>
</head>
<body>
<button class="btn-print" onclick="window.print()">🖨️ Print / Save as PDF</button>
<div class="cert-container">
  <div class="cert-header">TruProjects Academy</div>
  <div class="cert-badge">Official Certificate of Completion</div>
  <div class="cert-body">This is proudly presented to</div>
  <div class="cert-name">{user_display}</div>
  <div class="cert-body">for successfully completing the specialized AI mastery curriculum</div>
  <div class="cert-course">{course_display}</div>
  <div class="cert-footer">
    <div class="signature-box">
      <div style="font-family: 'Brush Script MT', cursive; font-size: 24px; color: #4338ca;">TruProjects AI</div>
      <div class="signature-line"></div>
      <div style="font-size: 12px; color: #64748b;">Academic Director</div>
    </div>
    <div style="text-align: center;">
      <div style="width: 70px; height: 70px; border-radius: 50%; background: linear-gradient(135deg, #fbbf24, #f59e0b); display: inline-flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 12px; box-shadow: 0 4px 10px rgba(245,158,11,0.4); text-transform: uppercase;">VERIFIED</div>
    </div>
    <div class="signature-box">
      <div style="font-size: 14px; font-weight: 700; color: #1e293b;">{datetime.now().strftime('%B %d, %Y')}</div>
      <div class="signature-line"></div>
      <div style="font-size: 12px; color: #64748b;">Date of Issue</div>
    </div>
  </div>
</div>
</body>
</html>
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

@router.post("/progress", response_model=ProgressResponse)
def update_progress(
    progress_in: ProgressUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    progress = db.query(StudentProgress).filter(
        StudentProgress.user_id == current_user.id,
        StudentProgress.lesson_id == progress_in.lesson_id
    ).first()

    if not progress:
        progress = StudentProgress(
            user_id=current_user.id,
            course_id=progress_in.course_id,
            lesson_id=progress_in.lesson_id
        )
        db.add(progress)

    progress.is_completed = progress_in.is_completed
    progress.completed_at = datetime.utcnow() if progress_in.is_completed else None

    db.commit()
    db.refresh(progress)

    total_completed = db.query(StudentProgress).filter(
        StudentProgress.user_id == current_user.id,
        StudentProgress.is_completed == True
    ).count()

    if total_completed == 1:
        existing_badge = db.query(Badge).filter(
            Badge.user_id == current_user.id,
            Badge.badge_name == "First Steps"
        ).first()
        if not existing_badge:
            new_badge = Badge(user_id=current_user.id, badge_name="First Steps")
            db.add(new_badge)
            db.commit()

    return progress

from ..services.quiz_service import QuizService
from ..services.certificate_service import CertificateService

class RecordQuizRequest(BaseModel):
    topic: str
    score: int
    total_questions: int
    xp_earned: Optional[int] = 0

@router.post("/record_quiz")
def record_quiz_score(
    payload: RecordQuizRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return QuizService.record_quiz_score(
        user=current_user,
        topic=payload.topic,
        score=payload.score,
        total_questions=payload.total_questions,
        db=db
    )

@router.post("/certificate/{course_id}", response_model=CertificateResponse)
def claim_certificate(
    course_id: int,
    request: Request,
    score: Optional[int] = None,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course_title = course.title
    return CertificateService.issue_ai_skill_certificate(
        skill=course_title,
        user=current_user,
        db=db,
        score=score,
        base_url=str(request.base_url)
    )

@router.post("/certificate/ai/{skill}", response_model=CertificateResponse)
def claim_ai_certificate(
    skill: str,
    request: Request,
    score: Optional[int] = None,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    return CertificateService.issue_ai_skill_certificate(
        skill=skill,
        user=current_user,
        db=db,
        score=score,
        base_url=str(request.base_url)
    )
