# Live Server Reload Trigger 2
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import warnings
import uuid
import re
from datetime import datetime

# Suppress non-critical third-party deprecations
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
warnings.filterwarnings("ignore", message=".*LangChainDeprecationWarning.*")

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from dotenv import load_dotenv

# Import Local Modules
from utils.extractor import extract_text_from_file
from utils.analyzer import (
    extract_skills, get_missing_skills, calculate_match, calculate_ml_match, 
    get_job_links, run_full_ai_analysis, generate_course_ai_explanation,
    generate_crash_course, generate_video_script, answer_user_doubt, analyze_live_project
)
from db import (
    init_db, create_user, verify_user, update_subscription, save_resume, 
    update_jd_score, log_user_action, get_user_certificates, get_user_quiz_results, 
    save_quiz_result, save_certificate, log_user_view, get_user_viewed_history, 
    get_all_certificates, get_all_users_extended, delete_user_by_email, update_user_role,
    has_user_completed_quiz
)

load_dotenv(override=True)

app = FastAPI(title="Unified AI Resume Analyzer & Learning Platform")

try:
    init_db()
except Exception as _e:
    print(f"init_db notice on startup: {_e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup static files and templates
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("certificates", exist_ok=True)
os.makedirs("uploads/videos", exist_ok=True)
os.makedirs("uploads/notes", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/learning_static", StaticFiles(directory="static"), name="learning_static")
app.mount("/certificates", StaticFiles(directory="certificates"), name="certificates")

templates = Jinja2Templates(directory="templates")

# Upload Validation Constraints
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}
ALLOWED_MEDIA_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".pdf", ".txt", ".doc", ".docx"}
MAX_RESUME_SIZE = 15 * 1024 * 1024  # 15MB
MAX_MEDIA_SIZE = 200 * 1024 * 1024  # 200MB

init_db()

@app.on_event("startup")
def startup_event():
    """Initializes tables and verifies default seed category exists."""
    try:
        from app.core.database import SessionLocal, engine
        from app.models.course import Base, Category
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        cat = db.query(Category).first()
        if not cat:
            cat = Category(name="Software & Tech", description="Curated Engineering & AI Courses")
            db.add(cat)
            db.commit()
        db.close()
    except Exception as e:
        print("[Startup Notice]:", e)


# Helper: Stateless Request-Scoped User Authentication
def get_user_from_request(request: Request):
    token = None
    cookie_tok = request.cookies.get("access_token")
    if cookie_tok and cookie_tok.strip() not in ("", "null", "undefined"):
        token = cookie_tok.strip()
    if not token:
        auth_hdr = request.headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            raw_tok = auth_hdr[7:].strip()
            if raw_tok not in ("", "null", "undefined"):
                token = raw_tok

    if not token:
        return None

    try:
        from jose import jwt
        from app.core.security import SECRET_KEY, ALGORITHM
        from app.core.database import SessionLocal
        from app.models.user import User as DBUser

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email and str(email).strip() not in ("", "null", "undefined"):
            clean_email = str(email).strip().lower()
            db = SessionLocal()
            user = db.query(DBUser).filter(DBUser.email == clean_email).first()
            db.close()
            return user
    except Exception as e:
        pass
    return None

def check_is_admin(request: Request) -> bool:
    user = get_user_from_request(request)
    if user and (getattr(user, 'role', '') or '').upper() == "ADMIN":
        return True
    return False

# ==========================================
# PUBLIC & AUTH ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="common/landing.html", context={"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_get(request: Request):
    return templates.TemplateResponse(request=request, name="common/signup.html", context={"request": request})

class SendOTPForm(BaseModel):
    email: str
    full_name: Optional[str] = None

@app.post("/api/auth/send-otp")
async def send_otp_endpoint(req: SendOTPForm):
    from app.services.email_service import is_valid_email_format, generate_otp, send_smtp_otp_email
    from app.core.database import SessionLocal
    from app.models.user import User

    clean_email = req.email.strip().lower()
    if not is_valid_email_format(clean_email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address format (e.g. name@example.com).")

    db = SessionLocal()
    existing = db.query(User).filter(User.email == clean_email).first()
    db.close()
    if existing:
        raise HTTPException(status_code=400, detail="This email is already registered. Please login instead.")

    otp = generate_otp(6)
    success, msg = send_smtp_otp_email(clean_email, otp, req.full_name)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "message": msg}

@app.post("/signup", response_class=HTMLResponse)
async def signup_post(
    request: Request, 
    full_name: str = Form(...), 
    email: str = Form(...), 
    ph_number: str = Form(""), 
    password: str = Form(...),
    otp: str = Form("")
):
    from app.services.email_service import is_valid_email_format, verify_otp
    clean_email = email.strip().lower()

    if not is_valid_email_format(clean_email):
        return templates.TemplateResponse(
            request=request, 
            name="common/signup.html", 
            context={"request": request, "error": "Invalid email address format.", "full_name": full_name, "email": email, "ph_number": ph_number}
        )

    if not otp or not otp.strip():
        return templates.TemplateResponse(
            request=request, 
            name="common/signup.html", 
            context={"request": request, "error": "Verification code (OTP) is required. Please click 'Get OTP'.", "full_name": full_name, "email": email, "ph_number": ph_number}
        )

    is_valid, msg = verify_otp(clean_email, otp.strip())
    if not is_valid:
        return templates.TemplateResponse(
            request=request, 
            name="common/signup.html", 
            context={"request": request, "error": msg, "full_name": full_name, "email": email, "ph_number": ph_number, "otp_sent": True}
        )

    success = create_user(full_name.strip(), clean_email, ph_number.strip(), password)
    if success:
        log_user_action(clean_email, "User Registered with Verified Email")
        return RedirectResponse(url="/login?registered=1", status_code=303)
    
    return templates.TemplateResponse(
        request=request, 
        name="common/signup.html", 
        context={"request": request, "error": "Email is already registered. Please login.", "full_name": full_name, "email": email, "ph_number": ph_number}
    )

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, registered: Optional[str] = None):
    success_msg = "Account verified and created successfully! Please log in." if registered else None
    return templates.TemplateResponse(
        request=request, 
        name="common/login.html", 
        context={"request": request, "success_msg": success_msg}
    )

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    clean_email = email.strip().lower()
    user = verify_user(clean_email, password)
    if user:
        from app.core.security import create_access_token
        access_token = create_access_token(subject=clean_email)
        log_user_action(clean_email, "User Logged In")
        response = RedirectResponse(url="/master", status_code=303)
        response.set_cookie(key="access_token", value=access_token, path="/", max_age=60*60*24*7, samesite="lax", httponly=False)
        return response
    return templates.TemplateResponse(request=request, name="common/login.html", context={"request": request, "error": "Invalid credentials"})

@app.get("/admin-login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    return templates.TemplateResponse(request=request, name="admin/admin_login.html", context={"request": request})

@app.post("/admin-login", response_class=HTMLResponse)
async def admin_login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    clean_email = email.strip().lower()
    user = verify_user(clean_email, password)
    if user and user.get("role") == "admin":
        from app.core.security import create_access_token
        access_token = create_access_token(subject=clean_email)
        log_user_action(clean_email, "Admin Logged In")
        response = RedirectResponse(url="/master", status_code=303)
        response.set_cookie(key="access_token", value=access_token, path="/", max_age=60*60*24*7, samesite="lax", httponly=False)
        return response
    return templates.TemplateResponse(request=request, name="admin/admin_login.html", context={"request": request, "error": "Invalid admin credentials or non-admin user"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token", path="/")
    return response

@app.get("/master", response_class=HTMLResponse)
async def master(request: Request):
    user = get_user_from_request(request)
    role = user.role.lower() if user else "user"
    is_subscribed = user.is_subscribed if user else False
    user_name = user.full_name if user else "Guest"
    user_email = user.email if user else ""
    return templates.TemplateResponse(
        request=request, 
        name="common/master.html", 
        context={
            "request": request, 
            "role": role, 
            "is_subscribed": is_subscribed,
            "user_name": user_name,
            "user_email": user_email
        }
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    user_name = user.full_name if user and user.full_name else "Scholar"
    user_email = user.email.strip().lower() if user and user.email else ""
    user_role = user.role.upper() if user and user.role else "STUDENT"
    is_subscribed = user.is_subscribed if user else False
    member_since = user.created_at.strftime("%b %Y") if (user and user.created_at) else "Active Member"

    from app.core.database import SessionLocal
    from app.models.user import User as UserModel
    from app.models.analysis import SystemLog, Resume, QuizResult
    from app.models.progress import Badge, Certificate
    from app.models.course import Course

    db = SessionLocal()
    try:
        # Check if user is an Administrator
        is_admin_user = (user_role == "ADMIN" or user_email == "shivanichittam666@gmail.com" or (user.role and user.role.lower() == "admin"))

        if is_admin_user:
            # === ADMIN STATS & ANALYTICS ===
            total_users = db.query(UserModel).count()
            total_resumes = db.query(Resume).count()
            total_courses = db.query(Course).filter(Course.is_published == True).count()
            pro_users_count = db.query(UserModel).filter(UserModel.is_subscribed == True).count()
            total_certs = db.query(Certificate).count()
            recent_users = db.query(UserModel).order_by(UserModel.id.desc()).limit(8).all()
            courses_list = db.query(Course).filter(Course.is_published == True).limit(6).all()
            
            recent_logs = db.query(SystemLog).order_by(SystemLog.id.desc()).limit(6).all()
            activities = []
            for log in recent_logs:
                activities.append({
                    "action": log.action,
                    "timestamp": log.timestamp.strftime("%b %d, %H:%M") if log.timestamp else "Recently"
                })
            if not activities:
                activities.append({"action": "Admin Session Initialized", "timestamp": "Today"})

            from app.models.subscription import Subscription
            from app.models.user import User as UserModel

            all_subs = db.query(Subscription).filter(
                (Subscription.payment_status == "SUCCESS") | (Subscription.is_active == True)
            ).all()

            total_revenue = 0.0
            subscribed_user_ids = set()
            for sub in all_subs:
                subscribed_user_ids.add(sub.user_id)
                coupon = (sub.coupon_code or "").strip().upper()
                if coupon == "FREE100":
                    total_revenue += 999.0
                elif coupon in ["DISCOUNT1500", "SAVE1500"]:
                    total_revenue += 1500.0
                else:
                    total_revenue += float(sub.amount or 0.0)

            pro_users_without_sub = db.query(UserModel).filter(
                UserModel.is_subscribed == True
            ).all()
            for u in pro_users_without_sub:
                if u.id not in subscribed_user_ids:
                    total_revenue += 1500.0

            admin_stats = {
                "total_users": total_users,
                "total_resumes": total_resumes,
                "total_courses": total_courses,
                "pro_users_count": pro_users_count,
                "total_certificates": total_certs,
                "total_revenue": round(total_revenue, 2),
                "formatted_revenue": f"₹{round(total_revenue, 2):,.2f}".replace(".00", "")
            }

            return templates.TemplateResponse(
                request=request, 
                name="admin/dashboard.html", 
                context={
                    "request": request, 
                    "name": user_name, 
                    "user_email": user_email,
                    "user_role": "ADMIN",
                    "is_subscribed": True,
                    "member_since": member_since,
                    "stats": admin_stats,
                    "recent_users": recent_users,
                    "courses_list": courses_list,
                    "activities": activities,
                    "top_skills": ["Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Redis", "CI/CD", "System Design", "React"]
                }
            )

        # === USER / CANDIDATE PERSONAL STATS ===
        from app.services.progress_service import ProgressService
        user_history = ProgressService.get_user_history_data(user, db) or {}
        
        # Latest resume
        latest_res = user_history.get("analysis")
        current_file = latest_res.get("filename") if latest_res else ""
        ats_score = latest_res.get("score", 0) if latest_res else 0
        missing_skills = user_history.get("missing_skills", [])
        
        # Badges
        raw_badges = db.query(Badge).filter(Badge.user_id == user.id).all() if user.id else []
        badges_list = []
        for b in raw_badges:
            badges_list.append({
                "name": b.badge_name, 
                "earned_at": b.earned_at.strftime("%b %d, %Y") if b.earned_at else "Active",
                "icon": "fa-award",
                "color": "#6366f1"
            })
        
        # Dynamic milestone badges if none explicitly in DB yet
        if not badges_list:
            if user_history.get("analyses"):
                badges_list.append({"name": "Resume Pioneer", "earned_at": "Unlocked", "icon": "fa-file-invoice", "color": "#3b82f6"})
            if ats_score >= 80:
                badges_list.append({"name": "ATS Top Tier (80%+)", "earned_at": "Unlocked", "icon": "fa-trophy", "color": "#10b981"})
            if user_history.get("quiz_results"):
                badges_list.append({"name": "Quiz Challenger", "earned_at": "Unlocked", "icon": "fa-bolt", "color": "#f59e0b"})
            if user_history.get("certificates"):
                badges_list.append({"name": "Certified Pro", "earned_at": "Unlocked", "icon": "fa-certificate", "color": "#8b5cf6"})
            if not badges_list:
                badges_list.append({"name": "Career Explorer", "earned_at": "Active", "icon": "fa-compass", "color": "#6366f1"})

        # Recent activities from SystemLog
        recent_logs = db.query(SystemLog).filter(
            SystemLog.user_email == user_email
        ).order_by(SystemLog.id.desc()).limit(6).all()
        
        activities = []
        for log in recent_logs:
            activities.append({
                "action": log.action,
                "timestamp": log.timestamp.strftime("%b %d, %H:%M") if log.timestamp else "Recently"
            })
            
        if len(activities) == 0:
            if latest_res:
                activities.append({
                    "action": f"Analyzed resume '{latest_res.get('filename')}' with {ats_score}% ATS score",
                    "timestamp": latest_res.get("created_at", "Recently")
                })
            activities.append({
                "action": "Logged into AI Career Dashboard",
                "timestamp": "Today"
            })

        # Recommended Courses from catalog
        recommended_courses = db.query(Course).filter(Course.is_published == True).limit(4).all()

        # Overall KPI aggregates
        courses_in_progress = user_history.get("courses", [])
        avg_course_progress = int(sum(c.get("progress", 0) for c in courses_in_progress) / len(courses_in_progress)) if courses_in_progress else 0
        quiz_results = user_history.get("quiz_results", [])
        quiz_pass_count = sum(1 for q in quiz_results if q.get("passed"))
        quiz_pass_rate = int((quiz_pass_count / len(quiz_results) * 100)) if quiz_results else 0
        mastery_xp = user_history.get("mastery_points", 0)
        certificates = user_history.get("certificates", [])

        stats = {
            "ats_score": ats_score,
            "resumes_count": len(user_history.get("analyses", [])),
            "courses_count": len(courses_in_progress),
            "avg_course_progress": avg_course_progress,
            "quizzes_count": len(quiz_results),
            "quiz_pass_rate": quiz_pass_rate,
            "certificates_count": len(certificates),
            "badges_count": len(badges_list),
            "mastery_xp": mastery_xp
        }

        return templates.TemplateResponse(
            request=request, 
            name="user/dashboard.html", 
            context={
                "request": request, 
                "name": user_name, 
                "user_email": user_email,
                "user_role": user_role,
                "is_subscribed": is_subscribed,
                "member_since": member_since,
                "current_file": current_file,
                "latest_resume": latest_res,
                "stats": stats,
                "courses_in_progress": courses_in_progress,
                "missing_skills": missing_skills,
                "badges": badges_list,
                "certificates": certificates,
                "activities": activities,
                "recommended_courses": recommended_courses
            }
        )

    except Exception as err:
        print("Dashboard load notice:", err)
        return templates.TemplateResponse(
            request=request,
            name="user/dashboard.html",
            context={
                "request": request,
                "name": user_name,
                "user_email": user_email,
                "user_role": user_role,
                "is_subscribed": is_subscribed,
                "member_since": member_since,
                "stats": {},
                "activities": []
            }
        )
    finally:
        db.close()

@app.get("/uploads/{filename}")
async def uploaded_file(filename: str):
    # Path traversal protection
    safe_name = os.path.basename(filename)
    file_path = os.path.join("uploads", safe_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    # Check Supabase Storage if file is not on local disk
    try:
        from utils.supabase_storage import get_supabase_file_url, resolve_bucket_name
        bucket = resolve_bucket_name(safe_name)
        dest_path = f"resumes/{safe_name}"
        sb_url = get_supabase_file_url(bucket, dest_path)
        if sb_url:
            return RedirectResponse(url=sb_url, status_code=307)
    except Exception as sb_err:
        print("Supabase redirect notice:", sb_err)
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/upload")
async def upload(request: Request, resume: UploadFile = File(...)):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
        
    from app.core.database import SessionLocal
    from app.services.resume_service import ResumeService
    from app.services.payment_service import PaymentService

    db = SessionLocal()
    try:
        quota_check = PaymentService.check_user_quota(user, "resumes", db)
        if not quota_check["allowed"]:
            import urllib.parse
            err_msg = urllib.parse.quote(quota_check["message"])
            return RedirectResponse(url=f"/dashboard?quota_error={err_msg}&upgrade_plan=Unlimited%20Pro", status_code=303)
            
        try:
            ResumeService.process_and_save_resume(resume, user, db)
        except HTTPException as he:
            import urllib.parse
            err_msg = urllib.parse.quote(he.detail)
            return RedirectResponse(url=f"/dashboard?upload_error={err_msg}", status_code=303)
    finally:
        db.close()

    return RedirectResponse(url="/extract_page", status_code=303)

@app.get("/extract_page", response_class=HTMLResponse)
async def extract_page(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.core.database import SessionLocal
    from app.models.analysis import Resume
    db = SessionLocal()
    clean_email = user.email.strip().lower() if user and user.email else None
    latest_res = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first() if clean_email else None

    if not latest_res:
        db.close()
        return templates.TemplateResponse(request=request, name="user/extract_page.html", context={"request": request, "text": "", "error": "No file uploaded yet."})

    extracted_text = latest_res.extracted_text
    # Self-healing: if extracted_text was not saved, extract from file on disk
    if not extracted_text or not extracted_text.strip():
        file_path = os.path.join("uploads", latest_res.filename)
        if os.path.exists(file_path):
            from utils.extractor import extract_text_from_file
            extracted_text = extract_text_from_file(file_path)
            if extracted_text and extracted_text.strip():
                latest_res.extracted_text = extracted_text
                db.commit()

    db.close()

    if not extracted_text or not extracted_text.strip():
        return templates.TemplateResponse(request=request, name="user/extract_page.html", context={"request": request, "text": "", "error": "No file uploaded yet or text could not be extracted."})

    return templates.TemplateResponse(request=request, name="user/extract_page.html", context={"request": request, "text": extracted_text, "filename": latest_res.filename})

@app.get("/analyze_page", response_class=HTMLResponse)
async def analyze_page(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.core.database import SessionLocal
    from app.models.analysis import Resume
    db = SessionLocal()
    clean_email = user.email.strip().lower() if user and user.email else None
    latest_res = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first() if clean_email else None

    if latest_res and (not latest_res.extracted_text or not latest_res.extracted_text.strip()):
        file_path = os.path.join("uploads", latest_res.filename)
        if os.path.exists(file_path):
            from utils.extractor import extract_text_from_file
            text = extract_text_from_file(file_path)
            if text and text.strip():
                latest_res.extracted_text = text
                db.commit()

    has_text = bool(latest_res and latest_res.extracted_text and latest_res.extracted_text.strip())
    db.close()

    if not has_text:
        return templates.TemplateResponse(request=request, name="user/analyze_page.html", context={"request": request, "error": "Please extract the text from your resume first."})

    return templates.TemplateResponse(request=request, name="user/analyze_page.html", context={"request": request})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, job_desc: str = Form(...)):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.core.database import SessionLocal
    from app.models.analysis import Resume
    from app.services.analysis_service import AnalysisService

    db = SessionLocal()
    clean_email = user.email.strip().lower() if user and user.email else None
    latest_res = db.query(Resume).filter(Resume.user_email == clean_email).order_by(Resume.id.desc()).first() if clean_email else None

    if latest_res and (not latest_res.extracted_text or not latest_res.extracted_text.strip()):
        file_path = os.path.join("uploads", latest_res.filename)
        if os.path.exists(file_path):
            from utils.extractor import extract_text_from_file
            text = extract_text_from_file(file_path)
            if text and text.strip():
                latest_res.extracted_text = text
                db.commit()

    if not latest_res or not latest_res.extracted_text or not latest_res.extracted_text.strip():
        db.close()
        return RedirectResponse(url="/analyze_page", status_code=303)

    extracted_text = latest_res.extracted_text
    analysis_res = AnalysisService.run_full_analysis(extracted_text, job_desc, user, db)
    db.close()

    ctx = {
        "request": request,
        "text": extracted_text,
        "is_subscribed": bool(user and user.is_subscribed),
        "user_email": user.email if user else "",
        **analysis_res
    }

    return templates.TemplateResponse(
        request=request,
        name="user/analysis.html",
        context=ctx
    )

@app.get("/download")
async def download_report(request: Request):
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.core.database import SessionLocal
    from app.models.analysis import Resume
    db = SessionLocal()
    latest_res = db.query(Resume).filter(Resume.user_email == user.email).order_by(Resume.id.desc()).first()
    db.close()

    score = latest_res.score if latest_res else 0
    missing = [s.strip() for s in latest_res.missing_skills.split(",") if s.strip()] if (latest_res and latest_res.missing_skills) else []

    file_path = f"report_{user.id}.pdf"
    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()
    content = []
    content.append(Paragraph("Resume Analysis Report", styles["Title"]))
    content.append(Spacer(1, 10))
    content.append(Paragraph(f"ML Match Score: {score}%", styles["Normal"]))
    content.append(Spacer(1, 10))
    content.append(Paragraph("Missing Skills:", styles["Heading2"]))
    content.append(Paragraph(", ".join(missing) if missing else "None", styles["Normal"]))
    doc.build(content)
    return FileResponse(file_path, filename="report.pdf")

# ==========================================
# LEARNING PLATFORM ROUTERS
# ==========================================

from app.api import auth, courses, lessons, subscriptions, chat, quizzes, gamification

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(courses.router, prefix="/api/courses", tags=["Courses"])
app.include_router(lessons.router, prefix="/api/lessons", tags=["Lessons"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(chat.router, prefix="/api/chat", tags=["AI Chat"])
app.include_router(quizzes.router, prefix="/api/quizzes", tags=["AI Assessments"])
app.include_router(gamification.router, prefix="/api/gamification", tags=["Gamification"])

@app.get("/learning/dashboard", response_class=HTMLResponse)
async def learning_dashboard(request: Request):
    user = get_user_from_request(request)
    role = user.role.lower() if user else "user"
    is_subscribed = user.is_subscribed if user else False
    
    local_missing_skills = []
    if user:
        from app.core.database import SessionLocal
        from app.models.analysis import Resume
        db = SessionLocal()
        latest_res = db.query(Resume).filter(Resume.user_email == user.email).order_by(Resume.id.desc()).first()
        db.close()
        if latest_res and latest_res.missing_skills:
            local_missing_skills = [s.strip() for s in latest_res.missing_skills.split(",") if s.strip()]

    try:
        from app.core.database import SessionLocal
        from app.models.course import Course
        db = SessionLocal()
        all_courses = db.query(Course).filter(Course.is_published == True).all()
        db.close()
    except Exception:
        all_courses = []

    return templates.TemplateResponse(
        request=request, 
        name="learning/dashboard.html", 
        context={
            "request": request, 
            "role": role, 
            "is_subscribed": is_subscribed,
            "missing_skills": local_missing_skills,
            "all_courses": all_courses
        }
    )

@app.get("/learning/history")
@app.get("/history")
async def learning_history(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.core.database import SessionLocal
    from app.services.progress_service import ProgressService

    db = SessionLocal()
    history_ctx = ProgressService.get_user_history_data(user, db)
    db.close()

    history_ctx["request"] = request
    history_ctx["role"] = user.role.lower()
    history_ctx["is_subscribed"] = user.is_subscribed

    return templates.TemplateResponse(
        request=request, 
        name="user/history.html", 
        context=history_ctx
    )

@app.get("/learning/report", response_class=HTMLResponse)
async def learning_report(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.core.database import SessionLocal
    from app.models.analysis import Resume
    db = SessionLocal()
    latest_res = db.query(Resume).filter(Resume.user_email == user.email).order_by(Resume.id.desc()).first()
    db.close()

    local_score = latest_res.score if latest_res else 0
    local_missing = [s.strip() for s in latest_res.missing_skills.split(",") if s.strip()] if (latest_res and latest_res.missing_skills) else []
    extracted_text = latest_res.extracted_text if latest_res else "Historic Resume Data"

    return templates.TemplateResponse(
        request=request,
        name="user/analysis.html",
        context={
            "request": request,
            "text": extracted_text,
            "resume_skills": ["Extracted Resume Skills"],
            "missing_skills": local_missing,
            "score": local_score,
            "matched_pct": local_score,
            "missing_pct": max(0, 100 - local_score),
            "ai_suggestions": "Report loaded from user history.",
            "job_links": [],
            "interview_questions": "Loaded from history.",
            "is_subscribed": bool(user and user.is_subscribed),
            "user_email": user.email if user else ""
        }
    )

@app.get("/learning/course", response_class=HTMLResponse)
@app.get("/learning/player", response_class=HTMLResponse)
async def learning_course(
    request: Request, 
    title: Optional[str] = None, 
    skill: Optional[str] = None, 
    course_id: Optional[int] = None, 
    lesson_id: Optional[int] = None
):
    user = get_user_from_request(request)
    role = user.role.lower() if user else "user"
    is_subscribed = user.is_subscribed if user else False

    user_tier = "free"
    lesson_req_plan = "free"
    
    if user:
        if (user.role or "").lower() == "admin":
            user_tier = "admin"
        else:
            from app.core.database import SessionLocal
            from app.models.subscription import Subscription
            db_sub = SessionLocal()
            try:
                sub = db_sub.query(Subscription).filter(
                    Subscription.user_id == user.id,
                    Subscription.is_active == True
                ).order_by(Subscription.amount.desc()).first()
                if sub:
                    amt = float(sub.amount or 0)
                    pname = (sub.plan_name or "").lower()
                    if amt >= 4999.0 or "4999" in pname or "vip" in pname:
                        user_tier = "4999"
                    elif amt >= 999.0 or "999" in pname or "pro" in pname:
                        user_tier = "999"
                    elif amt >= 99.0 or "99" in pname or "starter" in pname or "basic" in pname:
                        user_tier = "99"
                    else:
                        user_tier = "99"
                elif user.is_subscribed:
                    user_tier = "99"
            finally:
                db_sub.close()

    db_course_title = None
    if course_id or lesson_id:
        try:
            from app.core.database import SessionLocal
            from app.models.course import Course, Lesson, Module
            db = SessionLocal()
            try:
                l_obj = None
                if lesson_id:
                    l_obj = db.query(Lesson).filter(Lesson.id == lesson_id).first()
                elif course_id:
                    l_obj = db.query(Lesson).join(Module).filter(Module.course_id == course_id).order_by(Lesson.order.asc()).first()
                
                if l_obj:
                    req_plan = (getattr(l_obj, "required_plan", None) or "").lower().strip()
                    if not req_plan:
                        order_val = getattr(l_obj, "order", 1) or 1
                        if order_val <= 2:
                            req_plan = "free"
                        elif order_val == 3:
                            req_plan = "999"
                        else:
                            req_plan = "4999"
                    lesson_req_plan = req_plan

                    if l_obj.module_id:
                        m_obj = db.query(Module).filter(Module.id == l_obj.module_id).first()
                        if m_obj and m_obj.course_id:
                            c_obj = db.query(Course).filter(Course.id == m_obj.course_id).first()
                            if c_obj:
                                db_course_title = c_obj.title
                    if not db_course_title and l_obj:
                        db_course_title = l_obj.title
            finally:
                db.close()
        except Exception:
            pass

    target_skill = (skill or title or db_course_title or "Software Engineering").strip()
    display_title = db_course_title or title or (f"{target_skill} Crash Course" if target_skill else "Master Course")
    if user and display_title:
        log_user_view(user.email, "Course View", display_title, f"Opened course learning player for {target_skill}")

    # Determine is_locked strictly based on required_plan vs user_tier
    is_locked = False
    if user_tier == "admin" or user_tier == "4999":
        is_locked = False
    elif lesson_req_plan in ["free", "0"]:
        is_locked = False
    elif lesson_req_plan == "99":
        is_locked = user_tier not in ["99", "999", "4999"]
    elif lesson_req_plan == "999":
        is_locked = user_tier not in ["999", "4999"]
    elif lesson_req_plan == "4999":
        is_locked = user_tier != "4999"
    else:
        is_locked = not is_subscribed and role != "admin"

    return templates.TemplateResponse(
        request=request, 
        name="learning/player.html", 
        context={
            "request": request, 
            "role": role, 
            "is_subscribed": is_subscribed,
            "is_locked": is_locked,
            "required_plan": lesson_req_plan,
            "user_tier": user_tier,
            "course_title": display_title,
            "skill": target_skill
        }
    )

class AICrashCourseRequest(BaseModel):
    skill: str

@app.api_route("/learning/ai_crash_course", methods=["GET", "POST"])
async def learning_ai_crash_course(request: Request, skill: Optional[str] = None, req: Optional[AICrashCourseRequest] = None):
    user = get_user_from_request(request)
    target_skill = (skill or (req.skill if req else None) or "Software Engineering").strip()
    course_html = generate_crash_course(target_skill)
    if user:
        log_user_view(user.email, "AI Crash Course", target_skill, f"Generated AI crash course for {target_skill}")
    return {"skill": target_skill, "course_html": course_html}

@app.post("/api/learning/ai-course/generate")
async def generate_ai_course_learning_alias(request: Request):
    from app.api.courses import generate_ai_course_endpoint, AICourseGenerateRequest
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    data = await request.json()
    req_obj = AICourseGenerateRequest(**data)
    return generate_ai_course_endpoint(req=req_obj, current_user=user)

@app.get("/learning/admin", response_class=HTMLResponse)
async def learning_admin(request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    user = get_user_from_request(request)
    return templates.TemplateResponse(request=request, name="admin/admin.html", context={"request": request, "role": user.role.lower(), "is_subscribed": user.is_subscribed})

class UpgradeRequest(BaseModel):
    coupon: Optional[str] = None
    payment_method: Optional[str] = "DEMO_QR_SCANNER"
    card_number: Optional[str] = None
    card_expiry: Optional[str] = None
    card_cvv: Optional[str] = None
    card_holder: Optional[str] = None
    upi_id: Optional[str] = None
    utr_number: Optional[str] = None
    bank_name: Optional[str] = None
    plan_name: Optional[str] = "AI Career Pro Membership"
    amount: Optional[float] = 19.99

@app.post("/upgrade")
async def upgrade_user(req: UpgradeRequest, request: Request):
    from app.core.database import SessionLocal
    from app.models.user import User as DBUser
    from app.services.payment_service import PaymentService

    db = SessionLocal()
    try:
        user = get_user_from_request(request)
        if not user:
            user = db.query(DBUser).first()
            if not user:
                user = DBUser(
                    email="student@antigravity.ai",
                    full_name="Scholar User",
                    password_hash="demo_hash",
                    role="user",
                    is_subscribed=False
                )
                db.add(user)
                db.commit()
                db.refresh(user)

        if req.utr_number or req.payment_method == "DIRECT_UPI_QR":
            return PaymentService.verify_upi_utr_payment(
                user=user,
                utr_number=req.utr_number or "123456789012",
                plan_name=req.plan_name or "AI Career Pro Membership",
                amount=req.amount,
                coupon_code=req.coupon,
                db=db
            )

        res = PaymentService.process_demo_payment(
            user=user,
            plan_name=req.plan_name or "AI Career Pro Membership",
            coupon_code=req.coupon,
            amount_paid=req.amount,
            payment_method=req.payment_method or "DEMO_QR_SCANNER",
            db=db
        )
        return res
    finally:
        db.close()


class AdminUserActionRequest(BaseModel):
    email: str

class AdminRoleUpdateRequest(BaseModel):
    email: str
    role: str

class AdminSubscriptionUpdateRequest(BaseModel):
    email: str
    is_subscribed: bool

class AdminCreateUserRequest(BaseModel):
    full_name: str
    email: str
    password: str
    role: Optional[str] = "user"
    is_subscribed: Optional[bool] = False

class AdminCreateCourseRequest(BaseModel):
    category_id: Optional[int] = 1
    title: str
    description: Optional[str] = ""
    language: Optional[str] = "English"
    difficulty_level: Optional[str] = "Intermediate"

class AdminDeleteCourseRequest(BaseModel):
    course_id: int

class CourseAIExplainRequest(BaseModel):
    course_title: str
    course_desc: Optional[str] = ""
    difficulty: Optional[str] = "Intermediate"
    current_lesson: Optional[str] = ""

@app.get("/admin/dashboard_data")
async def admin_dashboard_data(request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized. Admin privileges required.")
    
    from app.core.database import SessionLocal
    from app.models.analysis import Resume, SystemLog

    users = get_all_users_extended()
    certificates = get_all_certificates()
    views = get_user_viewed_history(limit=150)
    
    db = SessionLocal()
    db_resumes = db.query(Resume).order_by(Resume.id.desc()).all()
    resumes = {}
    for r in db_resumes:
        email = (r.user_email or "").lower()
        if email not in resumes:
            resumes[email] = []
        resumes[email].append({
            "id": r.id,
            "user_email": r.user_email,
            "filename": r.filename,
            "score": r.score,
            "missing_skills": r.missing_skills
        })
        
    db_logs = db.query(SystemLog).order_by(SystemLog.id.desc()).limit(100).all()
    logs = [{
        "id": l.id,
        "user_email": l.user_email,
        "action": l.action,
        "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else ""
    } for l in db_logs]
    from app.models.subscription import Subscription
    from app.models.user import User as UserModel
    all_subs = db.query(Subscription).filter(
        (Subscription.payment_status == "SUCCESS") | (Subscription.is_active == True)
    ).all()

    total_revenue = 0.0
    subscribed_user_ids = set()
    for sub in all_subs:
        subscribed_user_ids.add(sub.user_id)
        coupon = (sub.coupon_code or "").strip().upper()
        if coupon == "FREE100":
            total_revenue += 999.0
        elif coupon in ["DISCOUNT1500", "SAVE1500"]:
            total_revenue += 1500.0
        else:
            total_revenue += float(sub.amount or 0.0)

    pro_users_without_sub = db.query(UserModel).filter(
        UserModel.is_subscribed == True
    ).all()
    for u in pro_users_without_sub:
        if u.id not in subscribed_user_ids:
            total_revenue += 1500.0

    db.close()
    
    stats = {
        "total_users": len(users),
        "total_certificates": len(certificates),
        "total_resumes": sum(len(v) for v in resumes.values()),
        "total_views": len(views),
        "total_revenue": round(total_revenue, 2),
        "formatted_revenue": f"₹{round(total_revenue, 2):,.2f}".replace(".00", "")
    }
    
    return {
        "stats": stats,
        "users": users,
        "certificates": certificates,
        "views": views,
        "resumes": resumes,
        "logs": logs
    }

@app.post("/admin/create_user")
async def admin_create_user(req: AdminCreateUserRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    clean_email = req.email.strip().lower()
    success = create_user(req.full_name, clean_email, "0000000000", req.password, role=req.role or "user")
    if success:
        if req.is_subscribed:
            update_subscription(clean_email, True)
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin provisioned new user: {clean_email}")
        return {"success": True, "message": f"Account for {clean_email} provisioned successfully."}
    raise HTTPException(status_code=400, detail="Email already exists or failed to create user.")

@app.get("/admin/courses")
async def admin_get_courses(request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    try:
        from app.core.database import SessionLocal
        from app.models.course import Course, Module, Lesson
        db = SessionLocal()
        all_courses = db.query(Course).all()
        result = []
        for c in all_courses:
            # Gather all lessons across all modules of this course
            lessons = []
            for m in (c.modules or []):
                for l in (m.lessons or []):
                    has_n = bool(l.content_text and ("Notes:" in l.content_text or "Notes uploaded:" in l.content_text or "/uploads/notes/" in l.content_text))
                    lessons.append({
                        "lesson_id": l.id, 
                        "lesson_title": l.title, 
                        "order": l.order,
                        "has_video": bool(l.video_url),
                        "has_notes": has_n
                    })
            result.append({
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "difficulty_level": c.difficulty_level,
                "language": c.language,
                "is_published": c.is_published,
                "lessons": lessons,
                "first_lesson_id": lessons[0]["lesson_id"] if lessons else None
            })
        db.close()
        return {"courses": result}
    except Exception as e:
        return {"courses": [], "error": str(e)}

@app.post("/admin/create_course")
async def admin_create_course(req: AdminCreateCourseRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    if not req.title or not req.title.strip():
        raise HTTPException(status_code=400, detail="Course title cannot be empty.")
        
    from app.core.database import SessionLocal, engine
    from app.models.course import Base, Category, Course, Module, Lesson
    
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        cat = db.query(Category).first()
        if not cat:
            cat = Category(name="Software & Tech", description="Curated Engineering & AI Courses")
            db.add(cat)
            db.commit()
            db.refresh(cat)
        cat_id = cat.id
            
        clean_title = req.title.strip()
        clean_desc = req.description.strip() if (req.description and req.description.strip()) else f"Comprehensive hands-on course blueprint on {clean_title}."
        
        new_course = Course(
            title=clean_title,
            description=clean_desc,
            category_id=cat_id,
            level=req.difficulty_level or "Intermediate",
            difficulty_level=req.difficulty_level or "Intermediate",
            language=req.language or "English",
            is_published=True
        )
        db.add(new_course)
        db.flush()
        
        course_id = int(new_course.id)
        course_title = str(new_course.title)
        course_desc = str(new_course.description)
        
        mod = Module(course_id=course_id, title=f"Module 1: Core {course_title} Concepts", order=1)
        db.add(mod)
        db.flush()
        mod_id = int(mod.id)
        
        les = Lesson(module_id=mod_id, title=f"Lesson 1: Introduction to {course_title}", order=1, content_text=course_desc, required_plan="free")
        db.add(les)
        db.flush()
        lesson_id = int(les.id)

        db.commit()
        db.refresh(new_course)
        db.refresh(les)

        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin created course: {course_title}")
        return {
            "success": True, 
            "message": f"Course '{course_title}' created successfully!", 
            "course_id": course_id,
            "lesson_id": lesson_id
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create course: {str(e)}")
    finally:
        db.close()

@app.post("/admin/delete_course")
async def admin_delete_course(req: AdminDeleteCourseRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    from app.core.database import SessionLocal
    from app.models.course import Course, Module, Lesson
    db = SessionLocal()
    try:
        course = db.query(Course).filter(Course.id == req.course_id).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found.")
            
        try:
            from app.models.progress import UserProgress, Certificate
            from app.models.subscription import Subscription
            db.query(UserProgress).filter(UserProgress.course_id == course.id).delete()
            db.query(Certificate).filter(Certificate.course_id == course.id).delete()
            db.query(Subscription).filter(Subscription.course_id == course.id).delete()
        except Exception as rel_err:
            print("Notice cleaning related records on course delete:", rel_err)

        modules = db.query(Module).filter(Module.course_id == course.id).all()
        for m in modules:
            db.query(Lesson).filter(Lesson.module_id == m.id).delete()
        db.query(Module).filter(Module.course_id == course.id).delete()
        db.delete(course)
        db.commit()
        
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin deleted course ID #{req.course_id}")
        return {"success": True, "message": f"Course ID #{req.course_id} deleted successfully."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete course: {str(e)}")
    finally:
        db.close()

class AdminDeleteLessonRequest(BaseModel):
    lesson_id: int

class AdminUpdateLessonRequest(BaseModel):
    lesson_id: int
    title: str

@app.post("/admin/delete_lesson")
async def admin_delete_lesson(req: AdminDeleteLessonRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    from app.core.database import SessionLocal
    from app.models.course import Lesson
    db = SessionLocal()
    try:
        lesson = db.query(Lesson).filter(Lesson.id == req.lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        
        lesson_title = lesson.title
        db.delete(lesson)
        db.commit()
        
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin deleted lesson #{req.lesson_id} ({lesson_title})")
        return {"success": True, "message": f"Lesson '{lesson_title}' deleted successfully."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete lesson: {str(e)}")
    finally:
        db.close()

@app.post("/admin/update_lesson")
async def admin_update_lesson(req: AdminUpdateLessonRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    from app.core.database import SessionLocal
    from app.models.course import Lesson
    db = SessionLocal()
    try:
        lesson = db.query(Lesson).filter(Lesson.id == req.lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        
        lesson.title = req.title.strip()
        db.commit()
        db.refresh(lesson)
        
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin renamed lesson #{req.lesson_id} to '{lesson.title}'")
        return {"success": True, "message": f"Lesson updated to '{lesson.title}' successfully.", "title": lesson.title}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update lesson: {str(e)}")
    finally:
        db.close()

@app.post("/admin/upload_lesson_media")
async def admin_upload_lesson_media(
    request: Request,
    lesson_id: Optional[int] = Form(None),
    course_id: Optional[int] = Form(None),
    lesson_title: Optional[str] = Form(None),
    required_plan: Optional[str] = Form(None),
    create_new_lesson: Optional[bool] = Form(False),
    video: Optional[UploadFile] = File(None),
    notes: Optional[UploadFile] = File(None)
):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    from app.core.database import SessionLocal
    from app.models.course import Course, Module, Lesson
    from app.services.storage_service import StorageService
    
    db = SessionLocal()
    try:
        lesson = None
        
        # 1. If existing lesson ID is specified and not creating a new lesson
        if lesson_id and not create_new_lesson:
            lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
            
        # 2. If lesson not found or admin requested adding a new lesson to a course
        if not lesson:
            target_course = None
            if course_id:
                target_course = db.query(Course).filter(Course.id == course_id).first()
            if not target_course and lesson_id:
                # Try finding course from lesson if possible, else use first course
                target_course = db.query(Course).first()
                
            if not target_course:
                raise HTTPException(status_code=404, detail="Target course not found. Please select or create a course first.")
                
            # Find or create module for this course
            mod = db.query(Module).filter(Module.course_id == target_course.id).order_by(Module.order.desc()).first()
            if not mod:
                mod = Module(course_id=target_course.id, title=f"Module 1: {target_course.title} Core", order=1)
                db.add(mod)
                db.commit()
                db.refresh(mod)
                
            # Determine next lesson order
            existing_count = db.query(Lesson).filter(Lesson.module_id == mod.id).count()
            next_order = existing_count + 1
            default_title = f"Lesson {next_order}: {target_course.title} Part {next_order}"
            title_to_use = (lesson_title.strip() if lesson_title and lesson_title.strip() else default_title)
            
            # Default plan based on lesson order: 1-2 -> free, 3 -> 999, 4 -> 4999
            plan_default = "free"
            if next_order == 3:
                plan_default = "999"
            elif next_order >= 4:
                plan_default = "4999"

            lesson = Lesson(
                module_id=mod.id,
                title=title_to_use,
                order=next_order,
                content_text=f"Content for {title_to_use}",
                required_plan=required_plan if (required_plan and required_plan.strip()) else plan_default
            )
            db.add(lesson)
            db.commit()
            db.refresh(lesson)
            
        # Update lesson title and required_plan if explicitly provided
        if lesson_title and lesson_title.strip():
            lesson.title = lesson_title.strip()
        if required_plan and required_plan.strip():
            lesson.required_plan = required_plan.strip().lower()
            
        res_msg = []
        if video and video.filename:
            v_ext = os.path.splitext(video.filename)[1].lower()
            if v_ext not in ALLOWED_MEDIA_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Video format '{v_ext}' not allowed.")
                
            video_url = StorageService.upload_video(video, lesson_id=lesson.id)
            if not video_url:
                raise HTTPException(status_code=500, detail="Video file save verification failed.")
                
            lesson.video_url = video_url
            res_msg.append("Video uploaded successfully")
            print(f"[VIDEO] Saved video for lesson #{lesson.id}: {lesson.video_url}")
            
        if notes and notes.filename:
            n_ext = os.path.splitext(notes.filename)[1].lower()
            if n_ext not in ALLOWED_MEDIA_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"Notes format '{n_ext}' not allowed.")

            notes_url = StorageService.upload_notes(notes, lesson_id=lesson.id)
            lesson.content_text = f"Notes: {notes.filename}\nURL: {notes_url}"
            res_msg.append("Notes uploaded successfully")
            
            if n_ext == ".pdf":
                try:
                    os.makedirs("uploads/notes", exist_ok=True)
                    temp_pdf = os.path.join("uploads/notes", f"temp_rag_main_{lesson.id}.pdf")
                    notes.file.seek(0)
                    with open(temp_pdf, "wb") as f:
                        shutil.copyfileobj(notes.file, f)
                    notes.file.seek(0)
                    from app.ai.tutor import ingest_pdf_to_vectorstore
                    ingest_pdf_to_vectorstore(temp_pdf, lesson_id=lesson.id)
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
                    res_msg.append("FAISS RAG Index Built")
                except Exception as rag_err:
                    print("RAG Ingest notice:", rag_err)
                
        db.commit()
        db.refresh(lesson)
        saved_lesson_id = int(lesson.id)
        
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin updated lesson #{saved_lesson_id} ({lesson.title}) media/notes.")
        return {
            "success": True, 
            "message": " & ".join(res_msg) if res_msg else f"Lesson '{lesson.title}' updated successfully.", 
            "lesson_id": saved_lesson_id,
            "lesson_title": lesson.title,
            "video_url": lesson.video_url
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload media: {str(e)}")
    finally:
        db.close()

@app.get("/admin/lesson_media/{lesson_id}")
@app.get("/api/lessons/{lesson_id}/media")
def get_lesson_media(lesson_id: int):
    from app.core.database import SessionLocal
    from app.models.course import Lesson
    db = SessionLocal()
    try:
        lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=404, detail=f"Lesson #{lesson_id} not found")

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
                if f.startswith(f"lesson_{lesson_id}_") and f.endswith(".pdf"):
                    notes_url = f"/uploads/notes/{f}"
                    if not notes_name:
                        notes_name = f
                    break

        return {
            "success": True,
            "lesson_id": lesson.id,
            "title": lesson.title,
            "video_url": lesson.video_url,
            "has_video": bool(lesson.video_url),
            "notes_url": notes_url,
            "notes_name": notes_name or f"Lesson {lesson.id} PDF Notes",
            "has_notes": bool(notes_url),
            "content_text": lesson.content_text
        }
    finally:
        db.close()

@app.get("/api/courses/lookup_media")
def lookup_course_media(skill: Optional[str] = None, title: Optional[str] = None, course_id: Optional[int] = None, lesson_id: Optional[int] = None):
    from app.core.database import SessionLocal
    from app.models.course import Course, Lesson, Module
    db = SessionLocal()
    try:
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
        
        # Look up parent module and course
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
                            if "http://" in line or "https://" in line:
                                for part in line.split():
                                    if part.startswith("http"):
                                        l_notes_url = part
                                        break
                            elif "/uploads/notes/" in line:
                                for part in line.split():
                                    if "/uploads/notes/" in part:
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
                if "http://" in line or "https://" in line:
                    for part in line.split():
                        if part.startswith("http"):
                            notes_url = part
                            break
                elif "/uploads/notes/" in line:
                    for part in line.split():
                        if "/uploads/notes/" in part:
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
    finally:
        db.close()

@app.post("/admin/delete_user")
async def admin_delete_user(req: AdminUserActionRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    success = delete_user_by_email(req.email)
    if success:
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin deleted user: {req.email}")
        return {"success": True, "message": f"User {req.email} deleted successfully."}
    raise HTTPException(status_code=400, detail="Failed to delete user.")

@app.post("/admin/update_role")
async def admin_update_role(req: AdminRoleUpdateRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    success = update_user_role(req.email, req.role)
    if success:
        admin_user = get_user_from_request(request)
        log_user_action(admin_user.email if admin_user else "Admin", f"Admin updated role for {req.email} to {req.role}")
        return {"success": True, "message": f"Updated role for {req.email} to {req.role}"}
    raise HTTPException(status_code=400, detail="Failed to update user role.")

@app.post("/admin/update_subscription")
async def admin_update_subscription(req: AdminSubscriptionUpdateRequest, request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    update_subscription(req.email, req.is_subscribed)
    admin_user = get_user_from_request(request)
    log_user_action(admin_user.email if admin_user else "Admin", f"Admin set subscription for {req.email} to {req.is_subscribed}")
    return {"success": True, "message": f"Updated subscription status for {req.email}"}

@app.get("/admin/certificates")
async def admin_certificates(request: Request):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"certificates": get_all_certificates()}

@app.get("/admin/viewed_history")
async def admin_viewed_history(request: Request, email: Optional[str] = None):
    if not check_is_admin(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"views": get_user_viewed_history(user_email=email, limit=200)}

@app.post("/api/course_ai_explain")
async def api_course_ai_explain(req: CourseAIExplainRequest, request: Request):
    explanation = generate_course_ai_explanation(
        course_title=req.course_title,
        course_desc=req.course_desc or "",
        difficulty=req.difficulty or "Intermediate",
        current_lesson=req.current_lesson or ""
    )
    user = get_user_from_request(request)
    if user:
        log_user_view(user.email, "Course AI Explainer", req.course_title, f"Requested AI course explanation for {req.course_title}")
    return explanation

# ==============================================================================
# DYNAMIC AI LEARNING MODULES & LIVE PROJECT INTEGRATION
# ==============================================================================

class SkillRequest(BaseModel):
    skill: str

class AskAIRequest(BaseModel):
    skill: str
    question: str

class ProjectAnalysisRequest(BaseModel):
    repo_url: str
    project_desc: str = ""
    skills: list = []

@app.post("/api/generate_course")
async def api_generate_course(req: SkillRequest):
    html_content = generate_crash_course(req.skill)
    return {"content": html_content}

@app.post("/api/generate_video")
async def api_generate_video(req: SkillRequest):
    slides_array = generate_video_script(req.skill)
    return {"type": "slideshow", "slides": slides_array}

@app.post("/api/ask_ai")
async def api_ask_ai(req: AskAIRequest):
    html_content = answer_user_doubt(req.skill, req.question)
    return {"content": html_content}

@app.post("/api/analyze_project")
async def api_analyze_project(req: ProjectAnalysisRequest, request: Request):
    user = get_user_from_request(request)
    skills = req.skills
    analysis_data = analyze_live_project(req.repo_url, req.project_desc, skills)
    if user:
        log_user_action(user.email, f"Analyzed Live Project: {req.repo_url}")
    return analysis_data

# ==============================================================================
# QUIZ COMPLETION & REAL-TIME USER CERTIFICATE ISSUANCE API
# ==============================================================================

class QuizCompleteRequest(BaseModel):
    topic: str
    score: int
    total_questions: int = 5

def generate_certificate_file(user_name: str, topic: str, score_pct: int, cert_uuid: str):
    filepath = os.path.join("certificates", f"{cert_uuid}.html")
    issued_date = datetime.now().strftime("%B %d, %Y")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Certificate of Achievement - {user_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700&family=Outfit:wght@400;600;700;800&family=Pinyon+Script&display=swap" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #0f172a;
            font-family: 'Outfit', sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: #1e293b;
        }}
        .print-btn {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .cert-card {{
            width: 900px;
            height: 620px;
            background: #ffffff;
            border-radius: 16px;
            padding: 40px;
            box-sizing: border-box;
            position: relative;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
            border: 12px solid #1e1b4b;
            outline: 4px solid #f59e0b;
            text-align: center;
            overflow: hidden;
        }}
        .cert-border-inner {{
            border: 2px dashed #cbd5e1;
            height: 100%;
            padding: 30px 40px;
            box-sizing: border-box;
            position: relative;
            border-radius: 8px;
        }}
        .cert-title {{
            font-family: 'Cinzel', serif;
            font-size: 2rem;
            color: #1e1b4b;
            letter-spacing: 3px;
            margin-bottom: 5px;
            text-transform: uppercase;
        }}
        .cert-subtitle {{
            font-size: 1.1rem;
            color: #6366f1;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 25px;
        }}
        .cert-present {{
            font-size: 1rem;
            color: #64748b;
            margin-bottom: 10px;
        }}
        .cert-name {{
            font-size: 2.5rem;
            font-weight: 800;
            color: #0f172a;
            border-bottom: 2px solid #f59e0b;
            display: inline-block;
            padding: 0 30px 8px 30px;
            margin-bottom: 20px;
        }}
        .cert-desc {{
            font-size: 1.05rem;
            color: #475569;
            max-width: 650px;
            margin: 0 auto 15px auto;
            line-height: 1.5;
        }}
        .cert-course {{
            font-size: 1.6rem;
            font-weight: 800;
            color: #4338ca;
            margin-bottom: 25px;
        }}
        .cert-score-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            border: 1px solid #10b981;
            padding: 6px 18px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 25px;
        }}
        .cert-footer {{
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            position: absolute;
            bottom: 30px;
            left: 50px;
            right: 50px;
        }}
        .sig-block {{
            text-align: center;
        }}
        .sig-line {{
            width: 160px;
            height: 2px;
            background: #94a3b8;
            margin: 5px auto;
        }}
        .sig-script {{
            font-family: 'Pinyon Script', cursive;
            font-size: 1.8rem;
            color: #4338ca;
        }}
        .seal-badge {{
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #fbbf24, #d97706);
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: white;
            box-shadow: 0 8px 20px rgba(217, 119, 6, 0.4);
            font-weight: 800;
            font-size: 0.75rem;
            letter-spacing: 1px;
        }}
        .cert-id {{
            position: absolute;
            top: 15px;
            right: 20px;
            font-size: 0.75rem;
            color: #94a3b8;
            font-weight: 600;
        }}
        @media print {{
            .print-btn {{ display: none; }}
            body {{ background: white; padding: 0; }}
            .cert-card {{ box-shadow: none; border-width: 8px; }}
        }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()"><i class="fa-solid fa-print"></i> Print / Download PDF</button>
    <div class="cert-card">
        <div class="cert-id">VERIFIED ID: TP-CERT-{cert_uuid}</div>
        <div class="cert-border-inner">
            <div class="cert-title">TruProjects Academy</div>
            <div class="cert-subtitle">Official Certificate of Mastery</div>
            <div class="cert-present">This is proudly awarded to</div>
            <div class="cert-name">{user_name}</div>
            <div class="cert-desc">for successfully completing the 5-Question AI Skill Benchmark Examination and demonstrating professional competence in:</div>
            <div class="cert-course">{topic}</div>
            <div>
                <span class="cert-score-badge"><i class="fa-solid fa-circle-check"></i> Passed with {score_pct}% Score</span>
            </div>
            <div class="cert-footer">
                <div class="sig-block">
                    <div class="sig-script">TruProjects AI</div>
                    <div class="sig-line"></div>
                    <div style="font-size: 0.8rem; color: #64748b; font-weight: 600;">Academic Review Board</div>
                </div>
                <div class="seal-badge">
                    <i class="fa-solid fa-award" style="font-size: 1.5rem; margin-bottom: 2px;"></i>
                    VERIFIED
                </div>
                <div class="sig-block">
                    <div style="font-weight: 700; color: #1e293b; font-size: 0.95rem;">{issued_date}</div>
                    <div class="sig-line"></div>
                    <div style="font-size: 0.8rem; color: #64748b; font-weight: 600;">Issue Date</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    try:
        from utils.supabase_storage import upload_file_to_supabase
        sb_url = upload_file_to_supabase(filepath, bucket_name="certificates", destination_path=f"{cert_uuid}.html", content_type="text/html")
        if sb_url:
            return sb_url
    except Exception as sb_err:
        print("Supabase certificate upload notice:", sb_err)

    return f"/certificates/{cert_uuid}.html"

@app.post("/api/quiz/complete")
async def api_quiz_complete(req: QuizCompleteRequest, request: Request):
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    from app.core.database import SessionLocal
    from app.services.quiz_service import QuizService
    from app.services.certificate_service import CertificateService
    from app.services.payment_service import PaymentService

    db = SessionLocal()
    try:
        quota_check = PaymentService.check_user_quota(user, "quizzes", db)
        if not quota_check["allowed"]:
            return {
                "success": False,
                "quota_exceeded": True,
                "upgrade_plan": "Unlimited Pro",
                "upgrade_price": 4999.0,
                "message": quota_check["message"]
            }

        quiz_res = QuizService.record_quiz_score(user, req.topic, req.score, req.total_questions, db)
        score_pct = quiz_res["score"]
        passed = quiz_res["passed"]
        
        cert_data = None
        if passed:
            cert = CertificateService.issue_ai_skill_certificate(
                skill=req.topic,
                user=user,
                db=db,
                score=score_pct,
                base_url=str(request.base_url)
            )
            cert_data = {
                "title": cert.title,
                "cert_uuid": cert.cert_uuid,
                "certificate_url": cert.certificate_url,
                "score": cert.score,
                "user_name": cert.user_name,
                "issued_at": cert.issued_at.strftime("%B %d, %Y") if cert.issued_at else ""
            }
            
        return {
            "success": True,
            "topic": req.topic,
            "score_pct": score_pct,
            "passed": passed,
            "certificate": cert_data
        }
    finally:
        db.close()

@app.get("/api/user/certificates")
async def api_get_user_certificates(request: Request):
    user = get_user_from_request(request)
    certs = get_user_certificates(user.email) if user else []
    return {"certificates": certs}

@app.get("/api/quiz/check_status")
async def api_quiz_check_status(topic: str, request: Request):
    user = get_user_from_request(request)
    if not user:
        return {"participated": False}
    
    participated = has_user_completed_quiz(user.email, topic)
    return {"participated": participated}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
