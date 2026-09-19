"""
Official Certificate Generation, Verification, and Cloud Storage Service.
Generates ReportLab PDF certificates, uploads to Supabase Storage,
and records verified credentials in the database.
"""
import os
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request

from app.models.progress import Certificate
from app.models.analysis import QuizResult
from app.models.user import User

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

class CertificateService:
    @staticmethod
    def generate_pdf(user_name: str, title: str, output_path: str):
        """Generates a professional PDF achievement certificate using ReportLab."""
        user_display = user_name or "Valued Scholar"
        course_display = title or "AI Mastery Course"
        
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        if HAS_REPORTLAB:
            try:
                c = canvas.Canvas(output_path, pagesize=landscape(letter))
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
                c.drawCentredString(5.5*inch, 1.8*inch, "Issued by TruProjects Certification Authority • Verified Online")
                c.save()
                return
            except Exception as e:
                print(f"[CertificateService] ReportLab error: {e}")

        # HTML fallback if ReportLab fails
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"<html><body><h1>TruProjects Academy Certificate</h1><h2>{user_display}</h2><p>{course_display}</p></body></html>")

    @staticmethod
    def issue_ai_skill_certificate(
        skill: str,
        user: User,
        db: Session,
        score: Optional[int] = None,
        base_url: str = ""
    ) -> Certificate:
        """Issues, uploads to Supabase, and persists a verified certificate for an AI skill."""
        clean_skill = skill.strip().title()
        skill_title = f"{clean_skill} Skill Certification"
        user_display_name = user.full_name or (user.email.split('@')[0].title() if user.email else "Accomplished Scholar")

        # Check quiz participation
        quiz_res = db.query(QuizResult).filter(
            QuizResult.user_email == user.email.strip().lower(),
            QuizResult.topic.ilike(f"%{clean_skill}%")
        ).order_by(QuizResult.id.desc()).first()

        if score is not None and score >= 0:
            verified_score = min(100, max(0, score))
        elif quiz_res:
            verified_score = int((quiz_res.score / max(1, quiz_res.total_questions)) * 100) if quiz_res.score <= quiz_res.total_questions else quiz_res.score
        else:
            verified_score = 0

        # Enforce strict policy: Minimum 25% pass score required to earn/issue a certificate
        if verified_score < 25:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Certificate cannot be issued: A minimum passing score of 25% is required. Candidate scored {verified_score}%."
            )

        filename = f"{uuid.uuid4()}.pdf"
        filepath = os.path.join("certificates", filename)
        CertificateService.generate_pdf(user_display_name, f"AI Mastery: {clean_skill}", filepath)

        cert_url = f"{base_url.rstrip('/')}/certificates/{filename}" if base_url else f"/certificates/{filename}"

        # Upload to Supabase Storage
        try:
            from utils.supabase_storage import upload_file_to_supabase
            sb_url = upload_file_to_supabase(filepath, bucket_name="certificates", destination_path=filename, content_type="application/pdf")
            if sb_url:
                cert_url = sb_url
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
        except Exception as sb_err:
            print("[CertificateService] Supabase upload notice:", sb_err)

        cert_uuid = str(uuid.uuid4())[:8].upper()

        cert = db.query(Certificate).filter(
            Certificate.user_email == user.email.strip().lower(),
            Certificate.title == skill_title
        ).first()

        if not cert:
            cert = Certificate(
                user_id=user.id,
                user_email=user.email.strip().lower(),
                user_name=user_display_name,
                course_id=None,
                title=skill_title,
                score=verified_score,
                certificate_url=cert_url,
                cert_uuid=cert_uuid
            )
            db.add(cert)
        else:
            cert.score = verified_score
            cert.certificate_url = cert_url
            cert.cert_uuid = cert_uuid
            cert.user_name = user_display_name

        db.commit()
        db.refresh(cert)
        return cert

    @staticmethod
    def get_user_certificates(user_email: str, db: Session) -> List[Dict[str, Any]]:
        """Retrieves all certificates earned by a user."""
        if not user_email:
            return []
        certs = db.query(Certificate).filter(
            Certificate.user_email == user_email.strip().lower()
        ).order_by(Certificate.id.desc()).all()
        return [
            {
                "id": c.id,
                "user_email": c.user_email,
                "user_name": c.user_name,
                "title": c.title,
                "score": c.score,
                "certificate_url": c.certificate_url,
                "cert_uuid": c.cert_uuid,
                "issued_at": c.issued_at.strftime("%Y-%m-%d %H:%M:%S") if c.issued_at else ""
            }
            for c in certs
        ]
