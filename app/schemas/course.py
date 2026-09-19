from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- Lesson Schemas ---
class LessonCreate(BaseModel):
    title: str
    order: int = 0
    content_text: Optional[str] = None
    video_url: Optional[str] = None
    required_plan: Optional[str] = "free"

class LessonResponse(LessonCreate):
    id: int
    module_id: int
    required_plan: Optional[str] = "free"

    class Config:
        from_attributes = True

# --- Module Schemas ---
class ModuleCreate(BaseModel):
    title: str
    order: int = 0
    language: str = "English"

class ModuleResponse(ModuleCreate):
    id: int
    course_id: int
    lessons: List[LessonResponse] = []

    class Config:
        from_attributes = True

# --- Course Schemas ---
class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    level: str = "Beginner"
    duration_hours: float = 0.0

class CourseResponse(CourseCreate):
    id: int
    thumbnail: Optional[str] = None
    is_published: bool
    created_at: datetime
    modules: List[ModuleResponse] = []

    class Config:
        from_attributes = True

# --- Category Schemas ---
class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryResponse(CategoryCreate):
    id: int
    courses: List[CourseResponse] = []

    class Config:
        from_attributes = True
