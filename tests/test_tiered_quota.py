import pytest
from app.services.payment_service import PaymentService
from app.models.user import User
from app.models.course import Course
from app.models.analysis import Resume, UserView
from app.models.subscription import Subscription
from app.core.database import SessionLocal

def test_tiered_quota_logic():
    db = SessionLocal()
    try:
        # Create test user
        test_email = "test_quota_user@antigravity.ai"
        user = db.query(User).filter(User.email == test_email).first()
        if not user:
            user = User(
                email=test_email,
                full_name="Quota Test User",
                hashed_password="test",
                role="user",
                is_subscribed=False
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Cleanup existing test data for this email
        db.query(Resume).filter(Resume.user_email == test_email).delete()
        db.query(Subscription).filter(Subscription.user_id == user.id).delete()
        db.commit()
        user.is_subscribed = False
        db.commit()

        # 1. Test Course viewing for Free User (Should be blocked)
        course_quota = PaymentService.check_user_quota(user, "courses", db)
        assert course_quota["allowed"] == False
        assert "requires a subscription" in course_quota["message"]
        assert course_quota["upgrade_price"] == 99.0

        # 2. Test Resume Upload 1 to 5 (Should all be FREE)
        for i in range(5):
            res_quota = PaymentService.check_user_quota(user, "resumes", db)
            assert res_quota["allowed"] == True, f"Resume #{i+1} should be free"
            # Add a mock resume entry to increase usage
            mock_res = Resume(user_email=test_email, filename=f"res_{i}.pdf", extracted_text="test text", score=80)
            db.add(mock_res)
            db.commit()

        # 3. Test 6th Resume Upload as Free User (Should be BLOCKED, requires ₹99 Basic Pack)
        res_6_quota = PaymentService.check_user_quota(user, "resumes", db)
        assert res_6_quota["allowed"] == False
        assert "5 free resume uploads" in res_6_quota["message"]
        assert res_6_quota["upgrade_price"] == 99.0

        # 4. Subscribe to Basic Pack (₹99)
        sub_99 = Subscription(
            user_id=user.id,
            course_id=1,
            plan_name="Basic Pack",
            amount=99.0,
            payment_status="SUCCESS",
            is_active=True
        )
        db.add(sub_99)
        user.is_subscribed = True
        db.commit()

        # 5. Course viewing should NOW be allowed for Basic Pack subscriber
        course_quota_sub = PaymentService.check_user_quota(user, "courses", db)
        assert course_quota_sub["allowed"] == True

        # 6. Test Resumes 6 to 10 with Basic Pack (Should be ALLOWED)
        for i in range(5, 10):
            res_quota = PaymentService.check_user_quota(user, "resumes", db)
            assert res_quota["allowed"] == True, f"Resume #{i+1} should be allowed under Basic Pack"
            mock_res = Resume(user_email=test_email, filename=f"res_{i}.pdf", extracted_text="test text", score=80)
            db.add(mock_res)
            db.commit()

        # 7. Test 11th Resume Upload as Basic Pack User (Should be BLOCKED, requires ₹999 Pro Unlimited)
        res_11_quota = PaymentService.check_user_quota(user, "resumes", db)
        assert res_11_quota["allowed"] == False
        assert "10 resume upload limit" in res_11_quota["message"]
        assert res_11_quota["upgrade_price"] == 999.0

        # Cleanup
        db.query(Resume).filter(Resume.user_email == test_email).delete()
        db.query(Subscription).filter(Subscription.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()

    finally:
        db.close()
