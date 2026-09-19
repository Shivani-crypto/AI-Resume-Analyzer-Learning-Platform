"""
AI Course Generation, Validation, and Persistence Service.
Provides the central pipeline for:
1. Cache lookup in `generated_courses` table.
2. Skill-specific course generation with strict system prompts.
3. Semantic and structural validation.
4. Database persistence and cache invalidation on regeneration.
"""
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.ai.llm_client import execute_llm
from app.ai.validators import validate_generated_course_content
from app.models.generated_course import GeneratedCourse
from app.models.user import User

class AICourseService:
    @staticmethod
    def get_or_generate_course(
        skill: str,
        user: Optional[User],
        db: Session,
        force_regenerate: bool = False,
        language: str = "English",
        difficulty: str = "Intermediate",
        source_analysis_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves an existing generated course from the database cache,
        or generates a fresh validated course via the LLM pipeline.
        """
        if not skill or not skill.strip():
            raise HTTPException(status_code=400, detail="Skill parameter is required.")

        skill_clean = skill.strip().title()
        user_email = user.email.strip().lower() if user and user.email else "student@example.com"
        user_id = user.id if user else None

        # Check DB cache if not forcing regeneration
        if not force_regenerate:
            existing = db.query(GeneratedCourse).filter(
                GeneratedCourse.user_email == user_email,
                GeneratedCourse.skill.ilike(skill_clean)
            ).order_by(GeneratedCourse.id.desc()).first()

            if existing and existing.content_json:
                try:
                    course_data = json.loads(existing.content_json)
                    return {
                        "success": True,
                        "cached": True,
                        "skill": skill_clean,
                        "course": course_data
                    }
                except Exception as parse_err:
                    print(f"[AICourseService] Cache parse error: {parse_err}")

        # Generate fresh course
        course_data = AICourseService.generate_course_from_llm(
            skill=skill_clean,
            language=language,
            difficulty=difficulty
        )

        # Validate semantically
        is_valid, reason = validate_generated_course_content(skill_clean, course_data)
        if not is_valid:
            print(f"[AICourseService] Semantic validation notice for {skill_clean}: {reason}. Using authentic domain course.")
            from utils.analyzer import build_authentic_skill_course
            course_data = build_authentic_skill_course(skill_clean)

        # Persist to database
        content_json_str = json.dumps(course_data)
        course_title = course_data.get("title", f"{skill_clean} Crash Course")

        existing_record = db.query(GeneratedCourse).filter(
            GeneratedCourse.user_email == user_email,
            GeneratedCourse.skill.ilike(skill_clean)
        ).first()

        if existing_record:
            existing_record.content_json = content_json_str
            existing_record.language = language
            existing_record.difficulty = difficulty
            existing_record.title = course_title
            if source_analysis_id:
                existing_record.source_analysis_id = source_analysis_id
            if user_id:
                existing_record.user_id = user_id
        else:
            new_course = GeneratedCourse(
                user_email=user_email,
                user_id=user_id,
                skill=skill_clean,
                title=course_title,
                language=language,
                difficulty=difficulty,
                content_json=content_json_str,
                source_analysis_id=source_analysis_id
            )
            db.add(new_course)

        db.commit()

        return {
            "success": True,
            "cached": False,
            "skill": skill_clean,
            "course": course_data
        }

    @staticmethod
    def generate_course_from_llm(
        skill: str,
        language: str = "English",
        difficulty: str = "Intermediate",
        job_context: str = "",
        resume_context: str = ""
    ) -> Dict[str, Any]:
        """Directly invokes the LLM prompt to construct an authentic skill micro-course."""
        from utils.analyzer import generate_personalized_skill_course
        course = generate_personalized_skill_course(
            skill=skill,
            language=language,
            difficulty=difficulty,
            job_context=job_context,
            resume_context=resume_context
        )
        return course
