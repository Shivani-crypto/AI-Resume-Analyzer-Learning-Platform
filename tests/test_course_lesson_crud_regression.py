import io
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.course import Course, Category, Module, Lesson
from app.models.user import User

client = TestClient(app)

def test_course_and_lesson_duplication_regression():
    """
    Mandatory Regression Test (10-Step Sequence):
    1. Create Course A
    2. Create Lesson 1 (in Course A)
    3. Create Course B
    4. Create Lesson 2 (in Course B)
    5. Upload video using lesson_id = 2
    6. Verify Lesson 2 was updated with video URL
    7. Verify total courses remains 2 (no new course created)
    8. Verify total lessons remains 2 (no new lesson created)
    9. Verify Lesson 1 is unchanged
    10. Verify Lesson 2 media endpoint returns the video URL
    """
    db = SessionLocal()
    try:
        # Clean up existing test courses/modules/lessons for clean test state
        db.query(Lesson).delete()
        db.query(Module).delete()
        db.query(Course).delete()
        db.query(Category).delete()
        db.commit()

        # Create Category
        cat = Category(name="Regression Category", description="Test Category")
        db.add(cat)
        db.commit()
        db.refresh(cat)

        # 1. Create Course A
        course_a = Course(
            title="Course A",
            description="First Course",
            category_id=cat.id,
            difficulty_level="Beginner",
            is_published=True
        )
        db.add(course_a)
        db.commit()
        db.refresh(course_a)

        mod_a = Module(course_id=course_a.id, title="Module A", order=1)
        db.add(mod_a)
        db.commit()
        db.refresh(mod_a)

        # 2. Create Lesson 1 (in Course A)
        lesson_1 = Lesson(
            module_id=mod_a.id,
            title="Lesson 1",
            content_text="Original content 1",
            order=1,
            video_url=None
        )
        db.add(lesson_1)
        db.commit()
        db.refresh(lesson_1)
        lesson_1_id = lesson_1.id

        # 3. Create Course B
        course_b = Course(
            title="Course B",
            description="Second Course",
            category_id=cat.id,
            difficulty_level="Intermediate",
            is_published=True
        )
        db.add(course_b)
        db.commit()
        db.refresh(course_b)

        mod_b = Module(course_id=course_b.id, title="Module B", order=1)
        db.add(mod_b)
        db.commit()
        db.refresh(mod_b)

        # 4. Create Lesson 2 (in Course B)
        lesson_2 = Lesson(
            module_id=mod_b.id,
            title="Lesson 2",
            content_text="Original content 2",
            order=1,
            video_url=None
        )
        db.add(lesson_2)
        db.commit()
        db.refresh(lesson_2)
        lesson_2_id = lesson_2.id

        # Initial checks
        assert db.query(Course).count() == 2
        assert db.query(Lesson).count() == 2

    finally:
        db.close()

    # Create admin user for authorized uploads
    db_admin = SessionLocal()
    try:
        admin_user = db_admin.query(User).filter(User.email == "admin_reg@example.com").first()
        if not admin_user:
            admin_user = User(
                email="admin_reg@example.com",
                hashed_password="hashed_admin_pw",
                full_name="Regression Admin",
                role="admin",
                is_active=True
            )
            db_admin.add(admin_user)
            db_admin.commit()
            db_admin.refresh(admin_user)
        else:
            admin_user.role = "admin"
            db_admin.commit()
    finally:
        db_admin.close()

    from app.core.security import create_access_token
    admin_token = create_access_token("admin_reg@example.com")
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    # 5. Upload video using lesson_id = 2 via API
    fake_video_bytes = b"FAKE_MP4_VIDEO_STREAM_DATA_FOR_TESTING"
    upload_res = client.post(
        f"/api/lessons/{lesson_2_id}/upload-video",
        files={"video": ("lesson2_intro.mp4", io.BytesIO(fake_video_bytes), "video/mp4")},
        cookies={"access_token": admin_token},
        headers=auth_headers
    )
    print("UPLOAD RESPONSE:", upload_res.status_code, upload_res.text)
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert "video_url" in upload_data
    uploaded_video_url = upload_data["video_url"]
    assert uploaded_video_url.startswith("/uploads/videos/") or uploaded_video_url.startswith("http")

    # 6. Verify Lesson 2 was updated with video URL in database
    db_verify = SessionLocal()
    try:
        db_lesson_2 = db_verify.query(Lesson).filter(Lesson.id == lesson_2_id).first()
        assert db_lesson_2 is not None
        assert db_lesson_2.video_url == uploaded_video_url

        # 7. Verify total courses remains 2 (no new course created)
        assert db_verify.query(Course).count() == 2

        # 8. Verify total lessons remains 2 (no new lesson created)
        assert db_verify.query(Lesson).count() == 2

        # 9. Verify Lesson 1 is unchanged
        db_lesson_1 = db_verify.query(Lesson).filter(Lesson.id == lesson_1_id).first()
        assert db_lesson_1 is not None
        assert db_lesson_1.video_url is None
        assert db_lesson_1.title == "Lesson 1"

    finally:
        db_verify.close()

    # 10. Verify Lesson 2 media endpoint returns the video URL
    media_res = client.get(f"/api/lessons/{lesson_2_id}/media")
    assert media_res.status_code == 200
    media_data = media_res.json()
    assert media_data["lesson_id"] == lesson_2_id
    assert media_data["video_url"] == uploaded_video_url
    assert media_data["has_video"] is True

    # Also verify Lesson 1 media endpoint shows no video
    media_res_1 = client.get(f"/api/lessons/{lesson_1_id}/media")
    assert media_res_1.status_code == 200
    media_data_1 = media_res_1.json()
    assert media_data_1["lesson_id"] == lesson_1_id
    assert media_data_1["video_url"] is None
    assert media_data_1["has_video"] is False


def test_dynamic_multi_course_lesson_crud_isolation():
    """
    Dynamic Multi-Course Regression Test:
    Repeats the course and lesson creation + upload + isolation cycle for N courses.
    Ensures that for EVERY new course created:
      1. Creating Course K and its Lessons does not mutate or duplicate Course 1..(K-1).
      2. Uploading video/notes to any lesson in any course updates ONLY that exact lesson.
      3. Global course count and global lesson count remain strictly deterministic.
      4. Every lesson's media endpoint returns only its own uploaded media.
    """
    db = SessionLocal()
    try:
        # Reset DB state
        db.query(Lesson).delete()
        db.query(Module).delete()
        db.query(Course).delete()
        db.query(Category).delete()
        db.commit()

        # Create Category
        cat = Category(name="Multi-Course Catalog", description="Comprehensive dynamic testing category")
        db.add(cat)
        db.commit()
        db.refresh(cat)

        # Create admin user for authorized uploads
        admin_user = db.query(User).filter(User.email == "admin_reg@example.com").first()
        if not admin_user:
            admin_user = User(
                email="admin_reg@example.com",
                hashed_password="hashed_admin_pw",
                full_name="Regression Admin",
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        else:
            admin_user.role = "admin"
            db.commit()
    finally:
        db.close()

    from app.core.security import create_access_token
    admin_token = create_access_token("admin_reg@example.com")
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    num_courses = 5
    lessons_per_course = 3
    all_created_lessons = [] # list of (course_id, lesson_id, lesson_title)

    # 1. Dynamically create N courses with multiple lessons each
    for c_idx in range(1, num_courses + 1):
        db = SessionLocal()
        try:
            course = Course(
                title=f"Automated Course {c_idx}",
                description=f"Description for Course {c_idx}",
                category_id=cat.id,
                difficulty_level="Intermediate",
                is_published=True
            )
            db.add(course)
            db.commit()
            db.refresh(course)
            course_id = course.id

            module = Module(course_id=course_id, title=f"Module 1 for Course {c_idx}", order=1)
            db.add(module)
            db.commit()
            db.refresh(module)

            for l_idx in range(1, lessons_per_course + 1):
                lesson = Lesson(
                    module_id=module.id,
                    title=f"Course {c_idx} Lesson {l_idx}",
                    content_text=f"Initial notes for Course {c_idx} Lesson {l_idx}",
                    order=l_idx,
                    video_url=None
                )
                db.add(lesson)
                db.commit()
                db.refresh(lesson)
                all_created_lessons.append((course_id, lesson.id, lesson.title))

            # Verify cumulative counts after every new course addition
            assert db.query(Course).count() == c_idx
            assert db.query(Lesson).count() == c_idx * lessons_per_course
        finally:
            db.close()

    expected_total_courses = num_courses
    expected_total_lessons = num_courses * lessons_per_course

    # 2. Selectively upload videos to specific lessons across different courses
    # e.g., Lesson #2 in Course 1, Lesson #5 in Course 2, Lesson #9 in Course 3, Lesson #14 in Course 5
    target_indices = [1, 4, 8, 13]  # 0-indexed in all_created_lessons
    uploaded_video_urls = {}

    for idx in target_indices:
        course_id, target_lesson_id, lesson_title = all_created_lessons[idx]
        fake_video_bytes = f"VIDEO_DATA_FOR_COURSE_{course_id}_LESSON_{target_lesson_id}".encode("utf-8")

        upload_res = client.post(
            f"/api/lessons/{target_lesson_id}/upload-video",
            files={"video": (f"c{course_id}_l{target_lesson_id}.mp4", io.BytesIO(fake_video_bytes), "video/mp4")},
            cookies={"access_token": admin_token},
            headers=auth_headers
        )
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        assert "video_url" in upload_data
        video_url = upload_data["video_url"]
        uploaded_video_urls[target_lesson_id] = video_url

        # Verify that total courses and total lessons remain strictly constant after every upload
        db_chk = SessionLocal()
        try:
            assert db_chk.query(Course).count() == expected_total_courses, "Upload created an unwanted course!"
            assert db_chk.query(Lesson).count() == expected_total_lessons, "Upload created an unwanted duplicate lesson!"
        finally:
            db_chk.close()

    # 3. Comprehensive verification for EVERY single lesson across ALL courses
    db_verify = SessionLocal()
    try:
        assert db_verify.query(Course).count() == expected_total_courses
        assert db_verify.query(Lesson).count() == expected_total_lessons

        for course_id, lesson_id, lesson_title in all_created_lessons:
            db_lesson = db_verify.query(Lesson).filter(Lesson.id == lesson_id).first()
            assert db_lesson is not None
            assert db_lesson.title == lesson_title

            media_res = client.get(f"/api/lessons/{lesson_id}/media")
            assert media_res.status_code == 200
            media_data = media_res.json()
            assert media_data["lesson_id"] == lesson_id

            if lesson_id in uploaded_video_urls:
                # Targeted lesson must have the uploaded video
                expected_url = uploaded_video_urls[lesson_id]
                assert db_lesson.video_url == expected_url
                assert media_data["video_url"] == expected_url
                assert media_data["has_video"] is True
            else:
                # Untargeted lesson must be completely unmodified
                assert db_lesson.video_url is None
                assert media_data["video_url"] is None
                assert media_data["has_video"] is False
    finally:
        db_verify.close()


def test_admin_upload_multi_lesson_flow_per_course():
    """
    Test the user's exact workflow:
    1. Admin creates a new Course (e.g. Python Course) -> has initial Lesson 1.
    2. Admin uploads video + notes to that respected course (Lesson 1).
    3. Admin then uses course_id to upload ANOTHER video + notes (+ create_new_lesson) -> Lesson 2.
    4. Admin repeats for Lesson 3 in the same course.
    5. Admin creates another Course (e.g. React Course) and adds lessons to it.
    6. Verify course and lesson isolation, order, and media links.
    """
    db = SessionLocal()
    try:
        db.query(Lesson).delete()
        db.query(Module).delete()
        db.query(Course).delete()
        db.query(Category).delete()
        db.commit()

        cat = Category(name="Programming", description="Tech Courses")
        db.add(cat)
        db.commit()
        db.refresh(cat)

        admin_user = db.query(User).filter(User.email == "admin_flow@example.com").first()
        if not admin_user:
            admin_user = User(
                email="admin_flow@example.com",
                hashed_password="pw",
                full_name="Flow Admin",
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        else:
            admin_user.role = "admin"
            db.commit()
    finally:
        db.close()

    from app.core.security import create_access_token
    admin_token = create_access_token("admin_flow@example.com")
    auth_headers = {"Authorization": f"Bearer {admin_token}"}
    auth_cookies = {"access_token": admin_token}

    # 1. Create Course 1: Python
    res1 = client.post(
        "/admin/create_course",
        json={"title": "Python Deep Dive", "category_id": cat.id, "difficulty_level": "Beginner"},
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert res1.status_code == 200
    data1 = res1.json()
    course1_id = data1["course_id"]
    lesson1_id = data1["lesson_id"]

    # 2. Upload video + notes to Course 1, Lesson 1
    v1_bytes = b"PYTHON_LESSON_1_VIDEO_STREAM"
    n1_bytes = b"PYTHON_LESSON_1_NOTES_CONTENT"
    up1 = client.post(
        "/admin/upload_lesson_media",
        data={"course_id": str(course1_id), "lesson_id": str(lesson1_id), "create_new_lesson": "false"},
        files={
            "video": ("python_l1.mp4", io.BytesIO(v1_bytes), "video/mp4"),
            "notes": ("python_l1.txt", io.BytesIO(n1_bytes), "text/plain")
        },
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert up1.status_code == 200
    assert up1.json()["lesson_id"] == lesson1_id

    # 3. Add ANOTHER video + notes to Course 1 using course_id + create_new_lesson=true (Lesson 2)
    v2_bytes = b"PYTHON_LESSON_2_VIDEO_STREAM_OOP"
    n2_bytes = b"PYTHON_LESSON_2_NOTES_OOP"
    up2 = client.post(
        "/admin/upload_lesson_media",
        data={
            "course_id": str(course1_id),
            "create_new_lesson": "true",
            "lesson_title": "Lesson 2: Python OOP & Classes"
        },
        files={
            "video": ("python_l2.mp4", io.BytesIO(v2_bytes), "video/mp4"),
            "notes": ("python_l2.txt", io.BytesIO(n2_bytes), "text/plain")
        },
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert up2.status_code == 200
    lesson2_id = up2.json()["lesson_id"]
    assert lesson2_id != lesson1_id
    assert up2.json()["lesson_title"] == "Lesson 2: Python OOP & Classes"

    # 4. Add a 3rd lesson to Course 1
    v3_bytes = b"PYTHON_LESSON_3_VIDEO_STREAM_ASYNC"
    up3 = client.post(
        "/admin/upload_lesson_media",
        data={
            "course_id": str(course1_id),
            "create_new_lesson": "true",
            "lesson_title": "Lesson 3: Async Python"
        },
        files={
            "video": ("python_l3.mp4", io.BytesIO(v3_bytes), "video/mp4")
        },
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert up3.status_code == 200
    lesson3_id = up3.json()["lesson_id"]

    # Verify Course 1 now has exactly 3 lessons in the DB and course count is 1
    db_chk = SessionLocal()
    try:
        assert db_chk.query(Course).count() == 1
        c1_lessons = db_chk.query(Lesson).join(Module).filter(Module.course_id == course1_id).order_by(Lesson.order).all()
        assert len(c1_lessons) == 3
        assert [l.id for l in c1_lessons] == [lesson1_id, lesson2_id, lesson3_id]
        assert [l.order for l in c1_lessons] == [1, 2, 3]
        assert c1_lessons[0].video_url is not None
        assert c1_lessons[1].video_url is not None
        assert c1_lessons[2].video_url is not None
    finally:
        db_chk.close()

    # 5. Create Course 2: React
    res2 = client.post(
        "/admin/create_course",
        json={"title": "Modern React Mastery", "category_id": cat.id, "difficulty_level": "Intermediate"},
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert res2.status_code == 200
    course2_id = res2.json()["course_id"]
    react_lesson1_id = res2.json()["lesson_id"]

    # Add Lesson 2 to Course 2
    up_react2 = client.post(
        "/admin/upload_lesson_media",
        data={
            "course_id": str(course2_id),
            "create_new_lesson": "true",
            "lesson_title": "Lesson 2: React Hooks & State"
        },
        files={
            "video": ("react_l2.mp4", io.BytesIO(b"REACT_HOOKS_VIDEO"), "video/mp4")
        },
        cookies=auth_cookies,
        headers=auth_headers
    )
    assert up_react2.status_code == 200
    react_lesson2_id = up_react2.json()["lesson_id"]

    # Final Verification: 2 courses, Course 1 has 3 lessons, Course 2 has 2 lessons
    db_final = SessionLocal()
    try:
        assert db_final.query(Course).count() == 2
        assert db_final.query(Lesson).count() == 5

        # Check /admin/courses API response
        courses_res = client.get("/admin/courses", cookies=auth_cookies, headers=auth_headers)
        assert courses_res.status_code == 200
        courses_data = courses_res.json()["courses"]
        assert len(courses_data) == 2

        c1_data = next(c for c in courses_data if c["id"] == course1_id)
        assert len(c1_data["lessons"]) == 3
        assert c1_data["lessons"][0]["has_notes"] is True
        assert c1_data["lessons"][0]["has_video"] is True

        c2_data = next(c for c in courses_data if c["id"] == course2_id)
        assert len(c2_data["lessons"]) == 2

        # Verify lookup_media endpoint returns full multi-lesson hierarchy for player/user view
        lookup_res = client.get(f"/api/courses/lookup_media?course_id={course1_id}")
        assert lookup_res.status_code == 200
        lookup_data = lookup_res.json()
        assert lookup_data["success"] is True
        assert lookup_data["course_id"] == course1_id
        assert lookup_data["course_title"] == "Python Deep Dive"
        assert len(lookup_data["lessons"]) == 3
        assert lookup_data["lessons"][0]["lesson_id"] == lesson1_id
        assert lookup_data["lessons"][1]["lesson_id"] == lesson2_id
        assert lookup_data["lessons"][2]["lesson_id"] == lesson3_id
        assert lookup_data["lessons"][0]["has_video"] is True
        assert lookup_data["lessons"][0]["has_notes"] is True
    finally:
        db_final.close()


