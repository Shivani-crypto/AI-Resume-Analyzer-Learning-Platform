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
