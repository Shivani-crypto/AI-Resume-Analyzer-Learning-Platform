from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from .base import Base

class GeneratedCourse(Base):
    __tablename__ = "generated_courses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String, index=True, nullable=False)
    skill = Column(String, index=True, nullable=False)
    source_analysis_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)
    language = Column(String, default="English")
    difficulty = Column(String, default="Intermediate")
    title = Column(String, nullable=False)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
