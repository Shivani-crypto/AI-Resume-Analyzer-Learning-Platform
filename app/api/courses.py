from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os

from ..core.database import get_db
from ..models.user import User
from ..models.course import Category, Course, Module, Lesson
from ..schemas.course import (
    CategoryCreate, CategoryResponse,
    CourseCreate, CourseResponse,
    ModuleCreate, ModuleResponse,
    LessonCreate, LessonResponse
)
from .auth import get_current_user, get_current_user_optional, get_current_active_admin

router = APIRouter()

# --- Categories ---
@router.get("/categories", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()

@router.post("/admin/categories", response_model=CategoryResponse)
def create_category(category: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    db_cat = Category(**category.model_dump())
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

# --- Courses ---
@router.get("/courses", response_model=List[CourseResponse])
def get_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).filter(Course.is_published == True).all()
    return courses

@router.get("/courses/{course_id}", response_model=CourseResponse)
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

@router.post("/admin/courses", response_model=CourseResponse)
def create_course(course: CourseCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    """
    Creates exactly one course. Database generates course ID.
    Returns the actual course ID and data.
    """
    try:
        # Verify category exists or fallback to first
        cat = db.query(Category).filter(Category.id == course.category_id).first()
        if not cat:
            cat = db.query(Category).first()
            if not cat:
                cat = Category(name="General & Engineering", description="General courses")
                db.add(cat)
                db.commit()
                db.refresh(cat)
            course.category_id = cat.id

        db_course = Course(**course.model_dump())
        db.add(db_course)
        db.commit()
        db.refresh(db_course)
        _ = db_course.modules
        return CourseResponse.model_validate(db_course)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create course: {str(e)}")

@router.delete("/admin/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    """Deletes a course and all child modules and lessons."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        db.delete(course)
        db.commit()
        return {"success": True, "message": f"Course #{course_id} deleted successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete course: {str(e)}")

# --- Modules ---
@router.get("/courses/{course_id}/modules", response_model=List[ModuleResponse])
def get_course_modules(course_id: int, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course.modules

@router.post("/admin/courses/{course_id}/modules", response_model=ModuleResponse)
def create_module(course_id: int, module: ModuleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    """Creates a module belonging to the specified course."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    db_module = Module(**module.model_dump(), course_id=course_id)
    db.add(db_module)
    db.commit()
    db.refresh(db_module)
    return db_module

# --- Lessons ---
@router.post("/admin/modules/{module_id}/lessons", response_model=LessonResponse)
def create_lesson(module_id: int, lesson: LessonCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    """Creates a lesson belonging to the specified module."""
    module = db.query(Module).filter(Module.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    db_lesson = Lesson(**lesson.model_dump(), module_id=module_id)
    db.add(db_lesson)
    db.commit()
    db.refresh(db_lesson)
    return db_lesson

# --- Media Lookup ---
@router.get("/lookup_media")
def lookup_media_endpoint(
    skill: Optional[str] = None, 
    title: Optional[str] = None, 
    course_id: Optional[int] = None, 
    lesson_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Looks up lesson video and notes by lesson_id, course_id, or matching skill/title.
    """
    lesson = None
    # 1. Exact lesson_id
    if lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()

    # 2. Exact course_id
    if not lesson and course_id:
        crs = db.query(Course).filter(Course.id == course_id).first()
        if crs and crs.modules:
            for m in crs.modules:
                if m.lessons:
                    lesson = m.lessons[0]
                    break

    # 3. Match by skill or course title
    target_name = (title or skill or "").strip().lower()
    if not lesson and target_name:
        all_courses = db.query(Course).all()
        for c in all_courses:
            c_title_low = c.title.lower()
            if target_name in c_title_low or c_title_low in target_name:
                if c.modules:
                    for m in c.modules:
                        if m.lessons:
                            lesson = m.lessons[0]
                            break
                if lesson:
                    break

    if not lesson:
        return {
            "success": False,
            "has_media": False,
            "has_video": False,
            "has_notes": False,
            "message": "No specific lesson media found."
        }

    # Find parent course and all sibling lessons
    parent_course = None
    all_lessons_data = []
    
    mod = db.query(Module).filter(Module.id == lesson.module_id).first() if lesson.module_id else None
    if mod:
        parent_course = db.query(Course).filter(Course.id == mod.course_id).first()
    elif course_id:
        parent_course = db.query(Course).filter(Course.id == course_id).first()

    if parent_course:
        course_modules = db.query(Module).filter(Module.course_id == parent_course.id).order_by(Module.order).all()
        for m in course_modules:
            m_lessons = db.query(Lesson).filter(Lesson.module_id == m.id).order_by(Lesson.order).all()
            for l in m_lessons:
                l_notes_url = None
                l_notes_name = None
                if l.content_text:
                    for line in l.content_text.splitlines():
                        if "Notes uploaded:" in line:
                            l_notes_name = line.replace("Notes uploaded:", "").strip()
                        elif "Notes:" in line:
                            l_notes_name = line.replace("Notes:", "").strip()
                        if "http://" in line or "https://" in line or "/uploads/notes/" in line:
                            for part in line.split():
                                if part.startswith("http") or part.startswith("/uploads/notes/"):
                                    l_notes_url = part
                                    break
                if not l_notes_url and os.path.exists("uploads/notes"):
                    for f in os.listdir("uploads/notes"):
                        if f.startswith(f"lesson_{l.id}_") and f.endswith(".pdf"):
                            l_notes_url = f"/uploads/notes/{f}"
                            if not l_notes_name:
                                l_notes_name = f
                            break
                l_has_video = bool(l.video_url and str(l.video_url).strip())
                l_has_notes = bool(l_notes_url and str(l_notes_url).strip())
                all_lessons_data.append({
                    "lesson_id": l.id,
                    "title": l.title,
                    "order": l.order,
                    "module_id": m.id,
                    "module_title": m.title,
                    "has_video": l_has_video,
                    "has_notes": l_has_notes,
                    "video_url": l.video_url if l_has_video else None,
                    "notes_url": l_notes_url if l_has_notes else None,
                    "notes_name": l_notes_name or f"Lesson {l.id} PDF Notes",
                    "content_text": l.content_text
                })

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
            if f.startswith(f"lesson_{lesson.id}_") and f.endswith(".pdf"):
                notes_url = f"/uploads/notes/{f}"
                if not notes_name:
                    notes_name = f
                break

    has_video = bool(lesson.video_url and str(lesson.video_url).strip())
    has_notes = bool(notes_url and str(notes_url).strip())

    return {
        "success": True,
        "has_media": has_video or has_notes,
        "has_video": has_video,
        "has_notes": has_notes,
        "course_id": parent_course.id if parent_course else None,
        "course_title": parent_course.title if parent_course else None,
        "course_description": parent_course.description if parent_course else None,
        "lesson_id": lesson.id,
        "title": lesson.title,
        "video_url": lesson.video_url if has_video else None,
        "notes_url": notes_url if has_notes else None,
        "notes_name": notes_name or f"Lesson {lesson.id} PDF Notes",
        "content_text": lesson.content_text,
        "lessons": all_lessons_data if all_lessons_data else [{
            "lesson_id": lesson.id,
            "title": lesson.title,
            "order": lesson.order,
            "has_video": has_video,
            "has_notes": has_notes,
            "video_url": lesson.video_url if has_video else None,
            "notes_url": notes_url if has_notes else None,
            "notes_name": notes_name or f"Lesson {lesson.id} PDF Notes"
        }]
    }

# --- AI Course Generation ---
class SlideRequest(BaseModel):
    topic: str
    description: str = ""

class AICourseGenerateRequest(BaseModel):
    skill: str
    force_regenerate: bool = False
    language: str = "English"
    difficulty: str = "Intermediate"

@router.post("/ai-course/generate")
def generate_ai_course_endpoint(
    req: AICourseGenerateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generates or retrieves a persistent, validated AI course for the exact missing skill requested.
    """
    from app.services.ai_course_service import AICourseService
    return AICourseService.get_or_generate_course(
        skill=req.skill,
        user=current_user,
        db=db,
        force_regenerate=req.force_regenerate,
        language=req.language,
        difficulty=req.difficulty
    )

@router.post("/generate_slides")
def generate_slides(req: SlideRequest, current_user: User = Depends(get_current_user)):
    """
    Generates a dynamic AI presentation script (slides) for a given topic.
    """
    topic_clean = (req.topic or "Software Development").strip()
    from utils.analyzer import generate_personalized_skill_course
    res = generate_personalized_skill_course(topic_clean)
    if res.get("success") and "course" in res and "slides" in res["course"]:
        return {"slides": res["course"]["slides"]}
    raise HTTPException(
        status_code=503,
        detail=res.get("error", f"Failed to generate validated AI presentation slides for '{topic_clean}'.")
    )

