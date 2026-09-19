"""
Unified Database Interface module for AI Resume Analyzer & Learning Platform.
Uses SQLAlchemy with SessionLocal from app.core.database for unified persistence.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import engine, SessionLocal
from app.models.base import Base
from app.models.user import User
from app.models.course import Category, Course, Module, Lesson
from app.models.progress import StudentProgress, Certificate, Badge
from app.models.subscription import Subscription, Coupon
from app.models.analysis import Resume, QuizResult, UserView, SystemLog
from app.models.generated_course import GeneratedCourse
from app.core.security import get_password_hash, verify_password

def init_db():
    """Initializes all database tables in the primary unified database and seeds default coupons."""
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            columns_to_add = [
                ("users", "ph_number", "VARCHAR"),
                ("certificates", "user_email", "VARCHAR"),
                ("certificates", "user_name", "VARCHAR"),
                ("certificates", "title", "VARCHAR"),
                ("certificates", "score", "INTEGER"),
                ("certificates", "cert_uuid", "VARCHAR"),
                ("subscriptions", "plan_name", "VARCHAR"),
                ("subscriptions", "amount", "FLOAT"),
                ("subscriptions", "coupon_code", "VARCHAR"),
                ("subscriptions", "payment_method", "VARCHAR"),
                ("lessons", "required_plan", "VARCHAR DEFAULT 'free'"),
                ("lessons", "video_url", "VARCHAR"),
                ("lessons", "content_text", "TEXT"),
                ("courses", "difficulty_level", "VARCHAR DEFAULT 'Intermediate'"),
                ("courses", "language", "VARCHAR DEFAULT 'English'"),
                ("modules", "language", "VARCHAR DEFAULT 'English'")
            ]
            for tbl, col, col_type in columns_to_add:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        print("Schema column migration notice:", e)

    # Seed demo coupons
    db = SessionLocal()
    try:
        default_coupons = [
            {
                "code": "WELCOME50",
                "discount_type": "PERCENTAGE",
                "discount_value": 50.0,
                "minimum_amount": 0.0,
                "maximum_discount": 50.0,
                "is_active": True
            },
            {
                "code": "SAVE10",
                "discount_type": "FIXED",
                "discount_value": 10.0,
                "minimum_amount": 15.0,
                "is_active": True
            },
            {
                "code": "FREE100",
                "discount_type": "PERCENTAGE",
                "discount_value": 100.0,
                "minimum_amount": 0.0,
                "is_active": True
            },
            {
                "code": "ADMINPAID",
                "discount_type": "PERCENTAGE",
                "discount_value": 100.0,
                "minimum_amount": 0.0,
                "is_active": True
            },
            {
                "code": "PREMIUM2026",
                "discount_type": "PERCENTAGE",
                "discount_value": 100.0,
                "minimum_amount": 0.0,
                "is_active": True
            },
            {
                "code": "DISCOUNT1500",
                "discount_type": "FIXED",
                "discount_value": 1500.0,
                "minimum_amount": 1500.0,
                "is_active": True
            },
            {
                "code": "SAVE1500",
                "discount_type": "FIXED",
                "discount_value": 1500.0,
                "minimum_amount": 1500.0,
                "is_active": True
            },
            {
                "code": "INACTIVE30",
                "discount_type": "PERCENTAGE",
                "discount_value": 30.0,
                "minimum_amount": 0.0,
                "is_active": False
            }
        ]

        for c_data in default_coupons:
            exists = db.query(Coupon).filter(Coupon.code == c_data["code"]).first()
            if not exists:
                coupon = Coupon(**c_data)
                db.add(coupon)
            else:
                # Ensure discount amount is up to date
                if c_data["code"] in ("DISCOUNT1500", "SAVE1500"):
                    exists.discount_type = "FIXED"
                    exists.discount_value = 1500.0
                    exists.minimum_amount = 1500.0
                    exists.is_active = True
        db.commit()
    except Exception as e:
        db.rollback()
        print("Coupon seeding notice:", e)
    finally:
        db.close()


def get_user_usage_counts(email: str) -> Dict[str, int]:
    """Returns total counts of resume analyses, quizzes, certificates, and course views for a user."""
    if not email:
        return {"resumes": 0, "quizzes": 0, "certificates": 0, "courses": 0}
    clean_email = email.strip().lower()
    db = SessionLocal()
    try:
        resumes_count = db.query(Resume).filter(Resume.user_email == clean_email).count()
        quizzes_count = db.query(QuizResult).filter(QuizResult.user_email == clean_email).count()
        u_rec = db.query(User).filter(User.email == clean_email).first()
        from sqlalchemy import or_
        if u_rec:
            certificates_count = db.query(Certificate).filter(or_(Certificate.user_email == clean_email, Certificate.user_id == u_rec.id)).count()
        else:
            certificates_count = db.query(Certificate).filter(Certificate.user_email == clean_email).count()
        courses_count = db.query(UserView).filter(UserView.user_email == clean_email, UserView.item_type == "Course View").count()
        return {
            "resumes": resumes_count,
            "quizzes": quizzes_count,
            "certificates": certificates_count,
            "courses": courses_count
        }
    finally:
        db.close()


def log_user_action(email: str, action: str):
    if not email:
        return
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        log = SystemLog(user_email=clean_email, action=action)
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"log_user_action error: {e}")
    finally:
        db.close()

def save_resume(filename: str, text: str, user_email: Optional[str] = None):
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower() if user_email else None
        user = db.query(User).filter(User.email == clean_email).first() if clean_email else None
        resume = Resume(
            filename=filename,
            extracted_text=text,
            user_email=clean_email,
            user_id=user.id if user else None
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        return resume.id
    except Exception as e:
        db.rollback()
        print(f"save_resume error: {e}")
        return None
    finally:
        db.close()

def update_jd_score(jd: str, score: int, missing_skills: str = "", user_email: Optional[str] = None):
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower() if user_email else None
        user = db.query(User).filter(User.email == clean_email).first() if clean_email else None
        
        row = None
        if clean_email:
            row = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first()
        else:
            row = db.query(Resume).order_by(Resume.id.desc()).first()
            
        if row:
            row.jd = jd
            row.score = score
            row.missing_skills = missing_skills
            if user and not row.user_id:
                row.user_id = user.id
        else:
            row = Resume(
                filename="Uploaded_Resume.pdf",
                jd=jd,
                score=score,
                missing_skills=missing_skills,
                user_email=clean_email,
                user_id=user.id if user else None
            )
            db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"update_jd_score error: {e}")
    finally:
        db.close()

def create_user(full_name: str, email: str, ph_number: str, password: str, role: str = "user") -> bool:
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        existing = db.query(User).filter(User.email == clean_email).first()
        if existing:
            return False
            
        hashed_pw = get_password_hash(password)
        db_role = "ADMIN" if role.lower() == "admin" else "STUDENT"
        user = User(
            full_name=full_name.strip(),
            email=clean_email,
            ph_number=ph_number.strip() if ph_number else None,
            hashed_password=hashed_pw,
            role=db_role
        )
        db.add(user)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"create_user error: {e}")
        return False
    finally:
        db.close()

def verify_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        if not user:
            return None
        if verify_password(password, user.hashed_password):
            role_str = "admin" if user.role.upper() == "ADMIN" else "user"
            return {
                "id": user.id,
                "full_name": user.full_name,
                "role": role_str,
                "is_subscribed": user.is_subscribed
            }
        return None
    except Exception as e:
        print(f"verify_user error: {e}")
        return None
    finally:
        db.close()

def update_subscription(email: str, is_subscribed: bool):
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        if user:
            user.is_subscribed = is_subscribed
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"update_subscription error: {e}")
    finally:
        db.close()

def save_quiz_result(user_email: str, topic: str, score: int, total_questions: int = 5, passed: bool = True):
    if not user_email or user_email.strip() in ("", "null", "undefined"):
        return
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        q_res = QuizResult(
            user_email=clean_email,
            user_id=user.id if user else None,
            topic=topic,
            score=score,
            total_questions=total_questions,
            passed=passed
        )
        db.add(q_res)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"save_quiz_result error: {e}")
    finally:
        db.close()

def save_certificate(user_email: str, user_name: str, title: str, score: int, cert_url: str, cert_uuid: str):
    if not user_email or user_email.strip() in ("", "null", "undefined"):
        return
    # Strictly enforce minimum 25% passing score rule: do not issue or save 0% or <25% certificates
    if score is not None and score < 25:
        print(f"save_certificate rejected: score {score}% is below required 25% minimum.")
        return
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        
        existing = db.query(Certificate).filter(Certificate.user_email == clean_email, Certificate.title == title).first()
        if existing:
            existing.score = score
            existing.certificate_url = cert_url
            existing.cert_uuid = cert_uuid
            existing.user_name = user_name
            existing.issued_at = datetime.utcnow()
        else:
            cert = Certificate(
                user_email=clean_email,
                user_id=user.id if user else None,
                user_name=user_name,
                title=title,
                score=score,
                certificate_url=cert_url,
                cert_uuid=cert_uuid
            )
            db.add(cert)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"save_certificate error: {e}")
    finally:
        db.close()

def get_user_certificates(user_email: str = None) -> List[Dict[str, Any]]:
    if not user_email or str(user_email).strip() in ("", "null", "undefined"):
        return []
    db = SessionLocal()
    try:
        clean_email = str(user_email).strip().lower()
        # Ensure only certificates with >= 25% score are returned and clean up 0% test certificates
        db.query(Certificate).filter(Certificate.score < 25).delete()
        db.commit()
        
        certs = db.query(Certificate).filter(Certificate.user_email == clean_email, Certificate.score >= 25).order_by(Certificate.id.desc()).all()
        return [
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
    except Exception as e:
        print(f"get_user_certificates error: {e}")
        return []
    finally:
        db.close()

def get_user_quiz_results(user_email: str = None) -> List[Dict[str, Any]]:
    if not user_email or str(user_email).strip() in ("", "null", "undefined"):
        return []
    db = SessionLocal()
    try:
        clean_email = str(user_email).strip().lower()
        results = db.query(QuizResult).filter(QuizResult.user_email == clean_email).order_by(QuizResult.id.desc()).all()
        return [
            {
                "id": q.id,
                "user_email": q.user_email,
                "topic": q.topic,
                "score": q.score,
                "total_questions": q.total_questions,
                "passed": q.passed,
                "completed_at": q.completed_at.strftime("%Y-%m-%d %H:%M:%S") if q.completed_at else ""
            }
            for q in results
        ]
    except Exception as e:
        print(f"get_user_quiz_results error: {e}")
        return []
    finally:
        db.close()

def has_user_completed_quiz(user_email: str, topic: str) -> bool:
    if not user_email or str(user_email).strip() in ("", "null", "undefined"):
        return False
    db = SessionLocal()
    try:
        clean_email = str(user_email).strip().lower()
        clean_topic = str(topic).strip().lower()
        res = db.query(QuizResult).filter(
            QuizResult.user_email == clean_email,
            QuizResult.topic.ilike(f"%{clean_topic}%")
        ).first()
        return res is not None
    except Exception as e:
        print(f"has_user_completed_quiz error: {e}")
        return False
    finally:
        db.close()

def log_user_view(user_email: str, item_type: str, item_title: str, details: str = ""):
    if not user_email or user_email.strip() in ("", "null", "undefined"):
        user_email = "guest@truprojects.com"
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower()
        view = UserView(user_email=clean_email, item_type=item_type, item_title=item_title, details=details)
        db.add(view)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"log_user_view error: {e}")
    finally:
        db.close()

def get_user_viewed_history(user_email: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        query = db.query(UserView)
        if user_email and user_email.strip() not in ("", "null", "undefined"):
            query = query.filter(UserView.user_email == user_email.strip().lower())
        views = query.order_by(UserView.id.desc()).limit(limit).all()
        return [
            {
                "id": v.id,
                "user_email": v.user_email,
                "item_type": v.item_type,
                "item_title": v.item_title,
                "details": v.details,
                "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else ""
            }
            for v in views
        ]
    except Exception as e:
        print(f"get_user_viewed_history error: {e}")
        return []
    finally:
        db.close()

def get_all_certificates() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        # Purge and filter out any invalid/0% certificates (< 25%)
        db.query(Certificate).filter(Certificate.score < 25).delete()
        db.commit()

        certs = db.query(Certificate).filter(Certificate.score >= 25).order_by(Certificate.id.desc()).all()
        return [
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
    except Exception as e:
        print(f"get_all_certificates error: {e}")
        return []
    finally:
        db.close()

def get_all_users_extended() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id.desc()).all()
        result = []
        for u in users:
            clean_email = u.email.lower()
            resumes_count = db.query(Resume).filter(Resume.user_email == clean_email).count()
            from sqlalchemy import or_
            certs_count = db.query(Certificate).filter(or_(Certificate.user_email == clean_email, Certificate.user_id == u.id)).count()
            views_count = db.query(UserView).filter(UserView.user_email == clean_email).count()
            quizzes_count = db.query(QuizResult).filter(QuizResult.user_email == clean_email).count()

            from app.models.subscription import Subscription
            sub = db.query(Subscription).filter(
                Subscription.user_id == u.id,
                Subscription.is_active == True
            ).order_by(Subscription.id.desc()).first()

            if not sub:
                sub = db.query(Subscription).filter(
                    Subscription.user_id == u.id
                ).order_by(Subscription.id.desc()).first()

            pkg_name = sub.plan_name if sub and sub.plan_name else ("Pro Unlimited" if u.is_subscribed else "Free Tier")
            amt_paid = float(sub.amount) if (sub and sub.amount is not None) else (999.0 if u.is_subscribed else 0.0)
            coupon = sub.coupon_code if (sub and sub.coupon_code) else None

            package_details = {
                "plan_name": pkg_name,
                "amount": amt_paid,
                "formatted_amount": f"₹{int(amt_paid)}" if amt_paid > 0 else "₹0 (Free)",
                "coupon_code": coupon,
                "payment_method": sub.payment_method if (sub and sub.payment_method) else ("Manual Admin" if u.is_subscribed else "None"),
                "payment_status": sub.payment_status if sub else ("SUCCESS" if u.is_subscribed else "FREE"),
                "transaction_id": sub.transaction_id if sub else None,
                "created_at": sub.created_at.strftime("%Y-%m-%d %H:%M") if (sub and getattr(sub, 'created_at', None)) else None
            }

            result.append({
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "ph_number": u.ph_number,
                "role": "admin" if u.role.upper() == "ADMIN" else "user",
                "is_subscribed": u.is_subscribed,
                "resumes_count": resumes_count,
                "certificates_count": certs_count,
                "views_count": views_count,
                "quizzes_count": quizzes_count,
                "package_details": package_details
            })
        return result
    except Exception as e:
        print(f"get_all_users_extended error: {e}")
        return []
    finally:
        db.close()

def delete_user_by_email(email: str) -> bool:
    if not email:
        return False
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        db.query(UserView).filter(UserView.user_email == clean_email).delete()
        db.query(QuizResult).filter(QuizResult.user_email == clean_email).delete()
        db.query(Certificate).filter(Certificate.user_email == clean_email).delete()
        db.query(Resume).filter(Resume.user_email == clean_email).delete()
        db.query(SystemLog).filter(SystemLog.user_email == clean_email).delete()
        db.query(User).filter(User.email == clean_email).delete()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"delete_user_by_email error: {e}")
        return False
    finally:
        db.close()

def update_user_role(email: str, role: str) -> bool:
    if not email or not role:
        return False
    db = SessionLocal()
    try:
        clean_email = email.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        if user:
            user.role = "ADMIN" if role.lower() == "admin" else "STUDENT"
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print(f"update_user_role error: {e}")
        return False
    finally:
        db.close()

def save_generated_course(user_email: str, skill: str, content_json: str, language: str = "English", difficulty: str = "Intermediate", source_analysis_id: Optional[int] = None, title: str = "") -> Optional[int]:
    if not user_email or not skill or not content_json:
        return None
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower()
        clean_skill = skill.strip().lower()
        user = db.query(User).filter(User.email == clean_email).first()
        
        course_title = title if title else f"{skill.strip().title()} Crash Course"
        existing = db.query(GeneratedCourse).filter(
            GeneratedCourse.user_email == clean_email,
            GeneratedCourse.skill.ilike(clean_skill)
        ).first()

        if existing:
            existing.content_json = content_json
            existing.language = language
            existing.difficulty = difficulty
            existing.title = course_title
            if source_analysis_id:
                existing.source_analysis_id = source_analysis_id
            if user:
                existing.user_id = user.id
            db.commit()
            db.refresh(existing)
            return existing.id
        else:
            gen_course = GeneratedCourse(
                user_email=clean_email,
                user_id=user.id if user else None,
                skill=skill.strip(),
                source_analysis_id=source_analysis_id,
                language=language,
                difficulty=difficulty,
                title=course_title,
                content_json=content_json
            )
            db.add(gen_course)
            db.commit()
            db.refresh(gen_course)
            return gen_course.id
    except Exception as e:
        db.rollback()
        print(f"save_generated_course error: {e}")
        return None
    finally:
        db.close()

def get_generated_course(user_email: str, skill: str) -> Optional[Dict[str, Any]]:
    if not user_email or not skill:
        return None
    db = SessionLocal()
    try:
        clean_email = user_email.strip().lower()
        clean_skill = skill.strip().lower()
        res = db.query(GeneratedCourse).filter(
            GeneratedCourse.user_email == clean_email,
            GeneratedCourse.skill.ilike(clean_skill)
        ).order_by(GeneratedCourse.id.desc()).first()
        if res:
            return {
                "id": res.id,
                "user_email": res.user_email,
                "user_id": res.user_id,
                "skill": res.skill,
                "title": res.title,
                "language": res.language,
                "difficulty": res.difficulty,
                "content_json": res.content_json,
                "created_at": res.created_at.strftime("%Y-%m-%d %H:%M:%S") if res.created_at else ""
            }
        return None
    except Exception as e:
        print(f"get_generated_course error: {e}")
        return None
    finally:
        db.close()