"""
Progress and History Aggregation Service.
Computes course completion rates, quiz records, earned certificates,
and mastery points across the learning platform.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.progress import StudentProgress, Certificate, Badge
from app.models.analysis import QuizResult, Resume
from app.models.course import Course, Lesson, Module
from app.models.user import User

class ProgressService:
    @staticmethod
    def get_user_history_data(user: User, db: Session) -> Dict[str, Any]:
        """Aggregates resumes, course completions, quizzes, certificates, and XP for a user."""
        if not user or not user.email:
            return {}

        clean_email = user.email.strip().lower()

        # Resumes
        raw_analyses = db.query(Resume).filter(
            Resume.user_email == clean_email
        ).order_by(Resume.id.desc()).all()
        
        analyses = []
        for r in raw_analyses:
            analyses.append({
                "id": r.id,
                "filename": r.filename,
                "score": r.score or 0,
                "match_score": r.score or 0,
                "job_role": r.jd if r.jd and len(r.jd.strip()) > 0 else "Software Engineer / Technical Role",
                "jd": r.jd if r.jd and len(r.jd.strip()) > 0 else "Software Engineer / Technical Role",
                "missing_skills": r.missing_skills or "",
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
            })
            
        latest_analysis = analyses[0] if analyses else None

        user_missing_skills = []
        if latest_analysis and latest_analysis.get("missing_skills"):
            user_missing_skills = [
                s.strip() for s in latest_analysis["missing_skills"].split(",") if s.strip()
            ]

        # Course progress from StudentProgress table
        progresses = db.query(StudentProgress).filter(
            StudentProgress.user_id == user.id
        ).all()

        courses_progress = []
        course_ids = list(set([p.course_id for p in progresses]))
        for cid in course_ids:
            course = db.query(Course).filter(Course.id == cid).first()
            if course:
                total_lessons = db.query(Lesson).join(Module).filter(Module.course_id == cid).count()
                completed_lessons = len([p for p in progresses if p.course_id == cid and p.is_completed])
                pct = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
                courses_progress.append({
                    "title": course.title,
                    "module": f"{completed_lessons}/{total_lessons} Lessons Completed",
                    "progress": pct
                })

        # Also check UserView table for course interactions to update stats dynamically
        from app.models.analysis import UserView
        user_views = db.query(UserView).filter(
            UserView.user_email == clean_email
        ).all()

        for uv in user_views:
            item_t = (uv.item_type or "").lower()
            title_t = (uv.item_title or "").strip()
            if "course" in item_t or "lesson" in item_t or "skill" in item_t or "view" in item_t or "quiz" in item_t:
                if title_t and not any(cp.get("title") == title_t for cp in courses_progress):
                    views_for_course = sum(1 for x in user_views if x.item_title == title_t)
                    calc_pct = min(100, max(25, views_for_course * 25))
                    courses_progress.append({
                        "title": title_t,
                        "module": f"{views_for_course} Interactions",
                        "progress": calc_pct
                    })

        # Quizzes
        quiz_records = db.query(QuizResult).filter(
            QuizResult.user_email == clean_email
        ).order_by(QuizResult.id.desc()).all()
        quiz_results = [
            {
                "id": q.id,
                "user_email": q.user_email,
                "topic": q.topic,
                "score": q.score,
                "total_questions": q.total_questions,
                "passed": q.passed,
                "completed_at": q.completed_at.strftime("%Y-%m-%d %H:%M:%S") if q.completed_at else ""
            }
            for q in quiz_records
        ]

        # Certificates (matching user_id or user_email)
        from sqlalchemy import or_
        certs = db.query(Certificate).filter(
            or_(
                Certificate.user_id == user.id,
                Certificate.user_email == clean_email
            )
        ).order_by(Certificate.id.desc()).all()
        user_certificates = [
            {
                "id": c.id,
                "user_email": c.user_email,
                "user_name": c.user_name,
                "title": c.title,
                "score": c.score,
                "certificate_url": c.certificate_url,
                "cert_uuid": c.cert_uuid,
                "issued_at": c.issued_at.strftime("%Y-%m-%d %H:%M:%S") if c.issued_at else ""
            }
            for c in certs
        ]

        # Subscription Plan & Eligibility
        from app.models.subscription import Subscription
        sub = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.is_active == True
        ).order_by(Subscription.id.desc()).first()

        plan_info = {
            "eligible_plan": "Free Tier Access",
            "plan_status": "Active (Free)",
            "tier": "free",
            "amount": "₹0",
            "badge_color": "#64748b",
            "badge_bg": "rgba(100, 116, 139, 0.12)",
            "is_admin": False,
            "benefits": [
                "1 Free Resume ATS Scan",
                "Access to Beginner Crash Courses",
                "Standard AI Tutor Assistance"
            ]
        }

        if (user.role and user.role.lower() == "admin") or clean_email == "shivanichittam666@gmail.com":
            plan_info = {
                "eligible_plan": "Super Admin VIP Access",
                "plan_status": "Active (Super Admin)",
                "tier": "admin",
                "amount": "Unlimited VIP",
                "badge_color": "#7e22ce",
                "badge_bg": "rgba(126, 34, 206, 0.12)",
                "is_admin": True,
                "benefits": [
                    "Full Executive Console Access",
                    "Unlimited Resume Scans & AI Analysis",
                    "All Course Videos & PDF Downloads",
                    "Official Verified Certifications"
                ]
            }
        elif sub or user.is_subscribed:
            pname = (sub.plan_name if sub and sub.plan_name else "Pro Unlimited Membership").strip()
            amt = float(sub.amount) if (sub and sub.amount is not None) else 0.0
            coupon = (sub.coupon_code if sub and sub.coupon_code else "").strip().upper()

            if coupon or amt == 0.0:
                coupon_display = coupon if coupon else "FREE99"
                amount_str = f"₹{int(amt)}" if amt > 0 else f"₹0 (100% Free with {coupon_display})"
                plan_info = {
                    "eligible_plan": f"{pname} ({amount_str})",
                    "plan_status": f"ACTIVE ({coupon_display})",
                    "tier": "pro" if "pro" in pname.lower() else "starter",
                    "amount": amount_str,
                    "coupon_code": coupon_display,
                    "badge_color": "#10b981",
                    "badge_bg": "rgba(16, 185, 129, 0.12)",
                    "is_admin": False,
                    "benefits": [
                        f"Unlocked via Promo Coupon ({coupon_display})",
                        "Full Video Lessons & PDF Notes",
                        "Unlimited ATS Resume Scans",
                        "Verified Skill Assessment Certificates"
                    ]
                }
            elif amt >= 4999.0 or "4999" in pname.lower() or "vip" in pname.lower():
                plan_info = {
                    "eligible_plan": f"{pname} (₹{int(amt)})",
                    "plan_status": "Active (VIP Lifetime)",
                    "tier": "vip",
                    "amount": f"₹{int(amt)}",
                    "coupon_code": coupon,
                    "badge_color": "#059669",
                    "badge_bg": "rgba(5, 150, 105, 0.12)",
                    "is_admin": False,
                    "benefits": [
                        "VIP Lifetime Course & Video Access",
                        "Unlimited Resume Scans & AI Analysis",
                        "All Verified Skill Certificates",
                        "Priority AI Tutor Assistance"
                    ]
                }
            elif amt >= 999.0 or "999" in pname.lower() or "pro" in pname.lower():
                plan_info = {
                    "eligible_plan": f"{pname} (₹{int(amt)})",
                    "plan_status": "Active (Pro Unlimited)",
                    "tier": "pro",
                    "amount": f"₹{int(amt)}",
                    "coupon_code": coupon,
                    "badge_color": "#2563eb",
                    "badge_bg": "rgba(37, 99, 235, 0.12)",
                    "is_admin": False,
                    "benefits": [
                        "Full Video Lessons & PDF Notes",
                        "Unlimited ATS Resume Scans",
                        "Verified Skill Assessment Certificates"
                    ]
                }
            else:
                plan_info = {
                    "eligible_plan": f"{pname} (₹{int(amt)})",
                    "plan_status": "Active (Starter)",
                    "tier": "starter",
                    "amount": f"₹{int(amt)}",
                    "coupon_code": coupon,
                    "badge_color": "#4338ca",
                    "badge_bg": "rgba(67, 56, 202, 0.12)",
                    "is_admin": False,
                    "benefits": [
                        "10 Resume Scans",
                        "Starter Course Catalog",
                        "5 Verified Skill Certificates"
                    ]
                }

        # Mastery Points: 25 XP per correct quiz question + 100 XP per certificate
        mastery_points = sum((int(q.get("score") or 0) * 25) for q in quiz_results) + (len(user_certificates) * 100)

        return {
            "analyses": analyses,
            "analysis": latest_analysis,
            "courses": courses_progress,
            "certificates": user_certificates,
            "quiz_results": quiz_results,
            "mastery_points": mastery_points,
            "missing_skills": user_missing_skills,
            "plan_info": plan_info,
            "user_name": user.full_name,
            "user_email": user.email
        }
