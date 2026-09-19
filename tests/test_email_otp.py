import pytest
from datetime import datetime, timedelta
from app.services.email_service import (
    is_valid_email_format,
    generate_otp,
    store_otp,
    verify_otp,
    _OTP_STORE
)

def test_valid_email_format():
    valid_cases = [
        "john.doe@example.com",
        "alex123@domain.co.in",
        "candidate+pro@techcompany.org",
        "name@sub.domain.edu"
    ]
    for email in valid_cases:
        assert is_valid_email_format(email) is True, f"Failed on valid email: {email}"

def test_invalid_email_format():
    invalid_cases = [
        "",
        "plainaddress",
        "#@%^%#$@#$@#.com",
        "@example.com",
        "Joe Smith <email@example.com>",
        "email.example.com",
        "email@example@example.com",
        "email@example",
        "email@example..com"
    ]
    for email in invalid_cases:
        assert is_valid_email_format(email) is False, f"Failed on invalid email: {email}"

def test_otp_generation():
    otp = generate_otp(6)
    assert len(otp) == 6
    assert otp.isdigit()

def test_otp_store_and_verify_success():
    email = "test.candidate@domain.com"
    otp = "654321"
    store_otp(email, otp, validity_minutes=5)
    
    is_valid, msg = verify_otp(email, otp)
    assert is_valid is True
    assert "successful" in msg.lower()

def test_otp_verify_wrong_code():
    email = "test.candidate2@domain.com"
    otp = "112233"
    store_otp(email, otp, validity_minutes=5)
    
    is_valid, msg = verify_otp(email, "999999")
    assert is_valid is False
    assert "invalid" in msg.lower()

def test_otp_verify_expired():
    email = "test.candidate3@domain.com"
    otp = "987654"
    # Artificially store an expired record
    _OTP_STORE[email] = {
        "otp": otp,
        "expires_at": datetime.now() - timedelta(seconds=10),
        "attempts": 0
    }
    
    is_valid, msg = verify_otp(email, otp)
    assert is_valid is False
    assert "expired" in msg.lower()
