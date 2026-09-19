import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.user import User

client = TestClient(app)

def test_user_registration_and_login():
    test_email = "testuser_suite@example.com"
    test_password = "SecurePassword123!"
    
    # 1. Clean up existing test user if present
    db = SessionLocal()
    db.query(User).filter(User.email == test_email).delete()
    db.commit()
    db.close()
    
    # 2. Register
    response = client.post("/signup", data={
        "full_name": "Test User",
        "email": test_email,
        "ph_number": "1234567890",
        "password": test_password
    }, follow_redirects=False)
    assert response.status_code == 303
    
    # 3. Login
    login_res = client.post("/login", data={
        "email": test_email,
        "password": test_password
    }, follow_redirects=False)
    assert login_res.status_code == 303
    assert "access_token" in login_res.cookies

def test_admin_authorization_protection():
    # Normal user should be rejected from admin endpoints with 403
    response = client.get("/admin/dashboard_data")
    assert response.status_code in (401, 403)
