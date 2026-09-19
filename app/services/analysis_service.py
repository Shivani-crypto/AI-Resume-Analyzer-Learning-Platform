"""
Resume and Job Description Analysis Service.
Coordinates skill extraction, TF-IDF cosine similarity, missing skill computation,
LLM-based interview preparation suggestions, and persistence of analysis results.
"""
import re
from typing import Dict, Any, List, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from utils.skill_normalizer import extract_skills, get_missing_skills, normalize_skill_name
from app.ai.llm_client import execute_llm
from app.models.analysis import Resume, SystemLog
from app.models.user import User

class AnalysisService:
    @staticmethod
    def calculate_ml_match(resume_text: str, job_description: str) -> float:
        """Computes TF-IDF cosine similarity between resume and job description."""
        if not resume_text or not resume_text.strip() or not job_description or not job_description.strip():
            return 0.0
        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform([resume_text, job_description])
            sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return round(float(sim) * 100, 2)
        except Exception as e:
            print(f"[AnalysisService] TF-IDF calculation error: {e}")
            return 0.0

    @staticmethod
    def get_job_links(skills: List[str]) -> Dict[str, str]:
        """Generates dynamic job search URLs based on extracted skills."""
        query = "+".join(skills[:5]) if skills else "software+engineer"
        return {
            "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={query}",
            "Indeed": f"https://www.indeed.com/jobs?q={query}",
            "Naukri": f"https://www.naukri.com/{query}-jobs"
        }

    @staticmethod
    def run_full_analysis(
        resume_text: str,
        job_desc: str,
        user: Optional[User],
        db: Session
    ) -> Dict[str, Any]:
        """
        Executes end-to-end skill matching, missing skill identification,
        TF-IDF scoring, and persists the analysis in the database.
        """
        score = AnalysisService.calculate_ml_match(resume_text, job_desc)
        job_skills = extract_skills(job_desc)
        resume_skills = extract_skills(resume_text)

        norm_resume_skills = {normalize_skill_name(s) for s in resume_skills if s.strip()}
        matched_skills = []
        missing_skills = []

        for skill in job_skills:
            if not skill.strip():
                continue
            if normalize_skill_name(skill) in norm_resume_skills:
                matched_skills.append(skill.title())
            else:
                missing_skills.append(skill.title())

        matched_skills = sorted(list(set(matched_skills)))
        missing_skills = sorted(list(set(missing_skills)))

        if not missing_skills:
            missing_skills = ["English Communication & Executive Soft Skills"]

        prompt_suggestions = f"""
        Candidate skills: {', '.join(resume_skills) if resume_skills else 'General Candidate'}.
        Job skills: {', '.join(job_skills) if job_skills else 'Software Engineering'}.
        Generate EXACTLY 5 short, actionable suggestions on how the candidate can improve their resume for this job.
        Return ONLY an HTML unordered list (<ul><li>...</li></ul>). Do NOT use markdown. Do NOT return JSON.
        """

        prompt_questions = f"""
        Job skills: {', '.join(job_skills) if job_skills else 'Software Engineering'}.
        Generate EXACTLY 5 technical interview questions to ask this candidate based on the required skills.
        Return ONLY an HTML ordered list (<ol><li>...</li></ol>). Do NOT use markdown. Do NOT return JSON.
        """

        sug_res = execute_llm(prompt_suggestions, "You are an expert AI Technical Recruiter.")
        que_res = execute_llm(prompt_questions, "You are an expert Technical Interviewer.")

        if not sug_res:
            sug_res = f"""<ul>
                <li>Highlight practical project experience with <strong>{', '.join(missing_skills[:3]) if missing_skills else 'core target technologies'}</strong>.</li>
                <li>Quantify your achievements with measurable business metrics (e.g. improved performance by 30%).</li>
                <li>Tailor your summary section to directly align with the job description keywords.</li>
                <li>Include links to live GitHub repositories or deployed applications.</li>
                <li>Ensure all relevant technical certifications are prominently listed at the top.</li>
            </ul>"""

        if not que_res:
            que_res = f"""<ol>
                <li>Explain the architecture and design patterns you commonly use in your projects.</li>
                <li>How do you approach performance optimization and debugging in production?</li>
                <li>Describe how you implement secure REST/GraphQL API communication.</li>
                <li>What strategies do you use for writing automated unit and integration tests?</li>
                <li>Walk us through a challenging technical problem you solved recently.</li>
            </ol>"""

        # Update latest resume record in database
        clean_email = user.email.strip().lower() if user and user.email else None
        if clean_email:
            res_row = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first()
            if res_row:
                res_row.jd = job_desc
                res_row.score = int(score)
                res_row.missing_skills = ",".join(missing_skills)
                if user and not res_row.user_id:
                    res_row.user_id = user.id
            else:
                res_row = Resume(
                    filename="Uploaded_Resume.pdf",
                    jd=job_desc,
                    score=int(score),
                    missing_skills=",".join(missing_skills),
                    user_email=clean_email,
                    user_id=user.id if user else None
                )
                db.add(res_row)

            log = SystemLog(user_email=clean_email, action=f"Generated AI Analysis Score: {score}%")
            db.add(log)
            db.commit()

        return {
            "score": score,
            "matched_pct": score,
            "missing_pct": max(0.0, round(100.0 - score, 2)),
            "resume_skills": matched_skills,
            "missing_skills": missing_skills,
            "ai_suggestions": sug_res.strip(),
            "interview_questions": que_res.strip(),
            "job_links": AnalysisService.get_job_links(matched_skills)
        }
