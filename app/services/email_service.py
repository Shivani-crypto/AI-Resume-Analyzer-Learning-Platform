import os
import re
import smtplib
import secrets
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Tuple, Optional

# In-memory OTP storage: { email: { "otp": str, "expires_at": datetime, "attempts": int } }
_OTP_STORE: Dict[str, Dict] = {}

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

def is_valid_email_format(email: str) -> bool:
    """Validates email format using strict RFC-compliant regex."""
    if not email or not isinstance(email, str):
        return False
    clean = email.strip()
    if len(clean) > 254 or len(clean) < 5:
        return False
    if not EMAIL_REGEX.match(clean):
        return False
    # Ensure domain has at least one dot and valid characters
    domain = clean.split('@')[-1]
    if '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        return False
    return True

def generate_otp(length: int = 6) -> str:
    """Generates a secure numeric OTP."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))

def store_otp(email: str, otp: str, validity_minutes: int = 10):
    """Stores OTP with expiration time in the cache."""
    clean_email = email.strip().lower()
    _OTP_STORE[clean_email] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=validity_minutes),
        "attempts": 0
    }

def verify_otp(email: str, user_otp: str) -> Tuple[bool, str]:
    """
    Verifies the user-submitted OTP against stored OTP.
    Returns (is_valid, message).
    """
    clean_email = email.strip().lower()
    record = _OTP_STORE.get(clean_email)
    
    if not record:
        return False, "No OTP request found for this email. Please request a new code."
        
    if datetime.now() > record["expires_at"]:
        _OTP_STORE.pop(clean_email, None)
        return False, "OTP has expired. Please request a new verification code."
        
    if record["attempts"] >= 5:
        _OTP_STORE.pop(clean_email, None)
        return False, "Too many failed attempts. Please request a new OTP."
        
    record["attempts"] += 1
    
    if record["otp"] == user_otp.strip():
        # Clean up OTP upon successful verification
        _OTP_STORE.pop(clean_email, None)
        return True, "Verification successful."
        
    return False, "Invalid verification code. Please check your email and try again."

def send_smtp_otp_email(to_email: str, otp_code: str, user_name: Optional[str] = None) -> Tuple[bool, str]:
    """
    Sends OTP email using configured SMTP credentials.
    Returns (success, message).
    """
    clean_email = to_email.strip().lower()
    
    # Read SMTP configuration from environment variables
    smtp_host = os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "smtp.gmail.com"
    smtp_port = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587")
    smtp_user = os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME") or ""
    smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or ""
    from_email = os.getenv("SMTP_FROM_EMAIL") or os.getenv("MAIL_FROM") or smtp_user or "noreply@aicareerpro.com"
    from_name = os.getenv("SMTP_FROM_NAME") or "AI Career Pro"
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")
    
    # Store OTP in memory regardless
    store_otp(clean_email, otp_code, validity_minutes=10)
    
    # If SMTP is not yet configured, log to console for development convenience
    if not smtp_user or not smtp_pass or "your_email" in smtp_user or "your_app_password" in smtp_pass:
        print(f"\n==========================================")
        print(f"[DEVELOPMENT MODE] SMTP Credentials Not Configured in .env")
        print(f"To: {clean_email}")
        print(f"Generated Registration OTP: {otp_code}")
        print(f"Valid for: 10 minutes")
        print(f"==========================================\n")
        return True, "Verification code generated. (SMTP not configured; OTP printed to server log for development testing)"

    display_name = user_name.strip() if user_name else "Candidate"
    
    # Build HTML Email Message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your AI Career Pro Verification Code: {otp_code}"
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = clean_email

    plain_text = f"""Hello {display_name},

Your verification code for AI Career Pro account registration is:

{otp_code}

This code is valid for 10 minutes. If you did not request this registration, please ignore this email.

Best regards,
The AI Career Pro Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Career Pro Verification Code</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #f8fafc; padding: 40px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06); border: 1px solid #e2e8f0;">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 32px 24px;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">
                                <span style="color: #3b82f6;">⚡</span> AI Career Pro
                            </h1>
                            <p style="color: #94a3b8; margin: 8px 0 0 0; font-size: 14px; font-weight: 500;">
                                Resume Analyzer & Career Advancement Platform
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 36px 32px;">
                            <h2 style="color: #0f172a; margin: 0 0 12px 0; font-size: 20px; font-weight: 700;">
                                Account Verification
                            </h2>
                            <p style="color: #475569; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
                                Hello <strong style="color: #0f172a;">{display_name}</strong>,<br>
                                Thank you for creating your account. Please use the verification code below to verify your email address and activate your registration:
                            </p>
                            
                            <!-- OTP Box -->
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px;">
                                <tr>
                                    <td align="center" style="background: #f1f5f9; border-radius: 12px; padding: 24px; border: 2px dashed #cbd5e1;">
                                        <div style="font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #1e293b; font-family: monospace;">
                                            {otp_code}
                                        </div>
                                        <div style="color: #64748b; font-size: 13px; font-weight: 600; margin-top: 8px;">
                                            ⏱ Valid for 10 minutes
                                        </div>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin: 0;">
                                <strong>Security Notice:</strong> Never share this code with anyone. If you did not initiate this registration request, you can safely ignore this email.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td align="center" style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 24px;">
                            <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                                &copy; {datetime.now().year} AI Career Pro. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            if use_tls:
                server.starttls()
                
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [clean_email], msg.as_string())
        server.quit()
        return True, "Verification code sent to your email successfully."
    except smtplib.SMTPAuthenticationError as e:
        print(f"[SMTP Error] Authentication failed for {smtp_user}: {e}")
        return False, "SMTP Authentication Failed: Please check your SMTP email and password in .env."
    except Exception as e:
        print(f"[SMTP Error] Could not send email: {e}")
        return False, f"Email delivery failed: {str(e)}"
