from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base
from .user import User

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String, index=True, nullable=True)
    filename = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    jd = Column(Text, nullable=True)
    score = Column(Integer, default=0)
    missing_skills = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")

class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String, index=True, nullable=True)
    topic = Column(String, nullable=False)
    score = Column(Integer, default=0)
    total_questions = Column(Integer, default=5)
    passed = Column(Boolean, default=True)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())

class UserView(Base):
    __tablename__ = "user_views"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=True)
    item_type = Column(String, nullable=False)
    item_title = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class SystemLog(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=True)
    action = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
