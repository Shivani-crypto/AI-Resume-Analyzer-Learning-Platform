from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import os
import uuid
import shutil

from ..core.database import get_db
from ..models.user import User
from ..models.course import Lesson, Module
from ..schemas.course import LessonResponse, LessonCreate
from ..services.storage_service import StorageService
from ..ai.tutor import ingest_pdf_to_vectorstore
from .auth import get_current_active_admin, get_current_user_optional

router = APIRouter()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_NOTES_EXTENSIONS = {".pdf", ".txt", ".doc", ".docx"}

@router.get("/{lesson_id}", response_model=LessonResponse)
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """Retrieves a single lesson by database ID."""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson

@router.get("/{lesson_id}/media")
def get_lesson_media(lesson_id: int, db: Session = Depends(get_db)):
    """Returns media and notes attached to a specific lesson."""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail=f"Lesson #{lesson_id} not found")

    notes_url = None
    notes_name = None
    if lesson.content_text:
        for line in lesson.content_text.splitlines():
            if "Notes uploaded:" in line:
                notes_name = line.replace("Notes uploaded:", "").strip()
            elif "Notes:" in line:
                notes_name = line.replace("Notes:", "").strip()
            if "http://" in line or "https://" in line or "/uploads/notes/" in line:
                for part in line.split():
                    if part.startswith("http") or part.startswith("/uploads/notes/"):
                        notes_url = part
                        break

    if not notes_url and os.path.exists("uploads/notes"):
        for f in os.listdir("uploads/notes"):
            if f.startswith(f"lesson_{lesson_id}_") and f.endswith(".pdf"):
                notes_url = f"/uploads/notes/{f}"
                if not notes_name:
                    notes_name = f
                break

    return {
        "success": True,
        "lesson_id": lesson.id,
        "title": lesson.title,
        "video_url": lesson.video_url,
        "has_video": bool(lesson.video_url),
        "notes_url": notes_url,
        "notes_name": notes_name or f"Lesson {lesson.id} PDF Notes",
        "has_notes": bool(notes_url),
        "content_text": lesson.content_text,
        "required_plan": getattr(lesson, "required_plan", "free") or "free"
    }

@router.post("/admin/lessons/{lesson_id}/upload-video")
@router.post("/{lesson_id}/upload-video")
async def upload_lesson_video(
    lesson_id: int, 
    video: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_active_admin)
) -> Dict[str, Any]:
    """
    Finds the existing lesson by ID and attaches the uploaded video URL.
    Updates the lesson in-place. Never creates a new course or lesson.
    """
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail=f"Lesson ID #{lesson_id} not found")

    ext = os.path.splitext(video.filename or "")[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported video format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}")

    try:
        video_url = StorageService.upload_video(video, lesson_id=lesson.id)
        if not video_url:
            raise HTTPException(status_code=500, detail="Failed to store video file.")

        lesson.video_url = video_url
        db.commit()
        db.refresh(lesson)

        return {
            "success": True,
            "lesson_id": lesson.id,
            "video_url": lesson.video_url,
            "message": "Video uploaded successfully"
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {str(e)}")

@router.post("/admin/lessons/{lesson_id}/upload-notes")
@router.post("/{lesson_id}/upload-notes")
async def upload_lesson_notes(
    lesson_id: int, 
    notes: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_active_admin)
) -> Dict[str, Any]:
    """
    Uploads a PDF/Document, attaches URL to existing lesson, and ingests into lesson RAG.
    """
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail=f"Lesson ID #{lesson_id} not found")

    ext = os.path.splitext(notes.filename or "")[1].lower()
    if ext not in ALLOWED_NOTES_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported document format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_NOTES_EXTENSIONS))}")

    try:
        notes_url = StorageService.upload_notes(notes, lesson_id=lesson.id)
        
        # Save temp file for RAG vectorstore indexing if PDF
        if ext == ".pdf":
            try:
                os.makedirs("uploads/notes", exist_ok=True)
                temp_pdf_path = os.path.join("uploads/notes", f"temp_rag_lesson_{lesson.id}.pdf")
                notes.file.seek(0)
                with open(temp_pdf_path, "wb") as buf:
                    shutil.copyfileobj(notes.file, buf)
                notes.file.seek(0)
                ingest_pdf_to_vectorstore(temp_pdf_path, lesson_id=lesson.id)
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
            except Exception as rag_err:
                print(f"[RAG Ingest Notice]: {rag_err}")

        lesson.content_text = f"Notes: {notes.filename}\nURL: {notes_url}"
        db.commit()
        db.refresh(lesson)

        return {
            "success": True,
            "lesson_id": lesson.id,
            "notes_url": notes_url,
            "message": "Notes uploaded and indexed successfully"
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload notes: {str(e)}")

@router.delete("/admin/lessons/{lesson_id}")
def delete_lesson(
    lesson_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_active_admin)
):
    """Deletes a lesson and removes its stored media."""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    try:
        if lesson.video_url:
            StorageService.delete_file(lesson.video_url)
        db.delete(lesson)
        db.commit()
        return {"success": True, "message": f"Lesson #{lesson_id} deleted."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete lesson: {str(e)}")

