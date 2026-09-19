"""
Resume Processing and Extraction Service.
Handles file validation, safe local persistence, cloud storage upload,
and multi-format text extraction (PDF, DOCX, Images/OCR).
"""
import os
import uuid
import shutil
from typing import Optional, Tuple
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from utils.extractor import extract_text_from_file
from app.models.analysis import Resume, SystemLog
from app.models.user import User

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}
MAX_RESUME_SIZE = 15 * 1024 * 1024  # 15 MB

class ResumeService:
    @staticmethod
    def process_and_save_resume(
        file: UploadFile,
        user: User,
        db: Session
    ) -> Tuple[str, str, Optional[str]]:
        """
        Validates file, extracts text, uploads to Supabase Storage,
        and saves resume record in the database.
        Returns: (safe_filename, extracted_text, supabase_url)
        """
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected.")

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_RESUME_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File extension '{ext}' not allowed. Allowed: PDF, DOCX, Image."
            )

        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_RESUME_SIZE:
            raise HTTPException(status_code=413, detail="File size exceeds 15MB limit.")

        os.makedirs("uploads", exist_ok=True)
        safe_filename = f"user_{user.id}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join("uploads", safe_filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        extracted_text = extract_text_from_file(filepath)
        if not extracted_text or not extracted_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from file. Ensure it is not empty or corrupted."
            )

        sb_url = None
        try:
            from utils.supabase_storage import upload_file_to_supabase, resolve_bucket_name
            bucket = resolve_bucket_name(safe_filename, file.content_type)
            dest = f"resumes/{safe_filename}"
            sb_url = upload_file_to_supabase(
                filepath,
                bucket_name=bucket,
                destination_path=dest,
                content_type=file.content_type
            )
        except Exception as e:
            print(f"[ResumeService] Supabase upload notice: {e}")

        clean_email = user.email.strip().lower() if user and user.email else None
        
        # Save or update Resume record with extracted text
        resume_record = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first() if clean_email else None
        if resume_record and not resume_record.score:
            # If user has an unanalyzed resume, update it with the newly uploaded file
            resume_record.filename = safe_filename
            resume_record.extracted_text = extracted_text
            resume_record.user_id = user.id if user else None
        else:
            # Create a fresh resume record
            resume_record = Resume(
                filename=safe_filename,
                extracted_text=extracted_text,
                user_email=clean_email,
                user_id=user.id if user else None
            )
            db.add(resume_record)

        log = SystemLog(user_email=clean_email or "anonymous", action=f"Uploaded Resume: {file.filename}")
        db.add(log)
        db.commit()
        db.refresh(resume_record)

        return safe_filename, extracted_text, sb_url

    @staticmethod
    def get_latest_resume(user: User, db: Session) -> Optional[Resume]:
        """Fetch the most recently uploaded resume for this user."""
        if not user or not user.email:
            return None
        return db.query(Resume).filter(
            Resume.user_email == user.email.strip().lower()
        ).order_by(Resume.id.desc()).first()
