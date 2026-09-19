from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    
    courses = relationship("Course", back_populates="category")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    level = Column(String, default="Beginner")
    difficulty_level = Column(String, default="Intermediate")
    language = Column(String, default="English")
    thumbnail = Column(String, nullable=True)
    duration_hours = Column(Float, default=0.0)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category", back_populates="courses")
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan")

class Module(Base):
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    title = Column(String, nullable=False)
    order = Column(Integer, default=0)
    language = Column(String, default="English") # e.g., English, Telugu, Hindi

    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan")

class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"))
    title = Column(String, nullable=False)
    order = Column(Integer, default=0)
    content_text = Column(Text, nullable=True) # Used for notes
    video_url = Column(String, nullable=True)
    required_plan = Column(String, default="free") # e.g., free, 99, 999, 4999
    
    module = relationship("Module", back_populates="lessons")
