import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.subscription import Coupon, Subscription
from app.models.user import User
from app.services.payment_service import PaymentService

client = TestClient(app)

def test_coupon_validation_percentage():
    """Test 50% discount coupon calculation"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "WELCOME50", "plan_name": "Pro Monthly", "amount": 20.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 10.0
    assert data["final_amount"] == 10.0

def test_coupon_validation_fixed():
    """Test fixed discount coupon calculation"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "SAVE10", "plan_name": "Lifetime", "amount": 50.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 10.0
    assert data["final_amount"] == 40.0

def test_coupon_validation_minimum_amount():
    """Test coupon with minimum purchase amount requirement"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "SAVE10", "plan_name": "Micro Plan", "amount": 5.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert "minimum purchase" in data["message"].lower()

def test_coupon_validation_invalid_code():
    """Test non-existent coupon code"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "NONEXISTENT999", "plan_name": "Pro Monthly", "amount": 20.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert "not found" in data["message"]

def test_coupon_validation_discount1500():
    """Test ₹1500 discount coupon on ₹4999 Unlimited Pro plan"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "DISCOUNT1500", "plan_name": "Unlimited Pro", "amount": 4999.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 1500.0
    assert data["final_amount"] == 3499.0

def test_coupon_validation_save1500():
    """Test ₹1500 discount coupon with alias SAVE1500"""
    res = client.post(
        "/api/subscriptions/coupons/validate",
        json={"code": "SAVE1500", "plan_name": "Unlimited Pro", "amount": 4999.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 1500.0
    assert data["final_amount"] == 3499.0

def test_subscription_plans_endpoint():
    """Test /api/subscriptions/plans returns Starter Pro (₹999) and Unlimited Pro (₹4999)"""
    res = client.get("/api/subscriptions/plans")
    assert res.status_code == 200
    data = res.json()
    assert "plans" in data
    assert "Starter Pro" in data["plans"]
    assert "Unlimited Pro" in data["plans"]
    assert data["plans"]["Starter Pro"]["price"] == 999.0
    assert data["plans"]["Starter Pro"]["limits"]["resumes"] == 5
    assert data["plans"]["Unlimited Pro"]["price"] == 4999.0
    assert data["plans"]["Unlimited Pro"]["limits"]["resumes"] is None

def test_upi_qr_config_endpoint():
    """Test /api/subscriptions/upi-qr-config with plan and coupon"""
    # Test Starter Pro (₹999)
    res = client.get("/api/subscriptions/upi-qr-config?plan_name=Starter%20Pro")
    assert res.status_code == 200
    data = res.json()
    assert data["amount"] == 999.0
    assert "upi://pay" in data["qr_string"]

    # Test Unlimited Pro with DISCOUNT1500 (₹4999 - ₹1500 = ₹3499)
    res = client.get("/api/subscriptions/upi-qr-config?plan_name=Unlimited%20Pro&coupon_code=DISCOUNT1500")
    assert res.status_code == 200
    data = res.json()
    assert data["amount"] == 3499.0
    assert data["discount"] == 1500.0
    assert "am=3499.00" in data["qr_string"]

def test_demo_payment_processing():
    """Test demo payment unlocks subscription and updates usage"""
    db = SessionLocal()
    try:
        # Create test user
        test_user = db.query(User).filter(User.email == "demo_pay_test@example.com").first()
        if not test_user:
            test_user = User(
                email="demo_pay_test@example.com",
                hashed_password="hashed_pw_test",
                full_name="Demo Pay Tester",
                is_active=True
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)

        # Process demo payment
        res = PaymentService.process_demo_payment(
            db=db,
            user_id=test_user.id,
            plan_name="Unlimited Pro",
            coupon_code="DISCOUNT1500",
            payment_method="upi_qr",
            amount_paid=3499.0
        )
        assert res["success"] is True
        assert res["is_subscribed"] is True
        assert res["final_amount"] == 3499.0

        # Verify subscription was persisted
        user_sub = db.query(Subscription).filter(Subscription.user_id == test_user.id).first()
        assert user_sub is not None
        assert user_sub.is_active is True
        assert user_sub.plan_name == "Unlimited Pro"
        assert user_sub.coupon_code == "DISCOUNT1500"

    finally:
        db.close()

