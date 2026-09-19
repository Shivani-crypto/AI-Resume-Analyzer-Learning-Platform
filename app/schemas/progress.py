from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ProgressUpdate(BaseModel):
    course_id: int
    lesson_id: int
    is_completed: bool

class ProgressResponse(BaseModel):
    id: int
    user_id: int
    course_id: int
    lesson_id: int
    is_completed: bool
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class CertificateResponse(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int] = None
    certificate_url: str
    issued_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BadgeResponse(BaseModel):
    id: int
    badge_name: str
    earned_at: datetime

    class Config:
        from_attributes = True
