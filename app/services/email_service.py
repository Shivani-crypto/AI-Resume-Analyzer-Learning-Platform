import os
import re
import json
import socket
import smtplib
import secrets
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Tuple, Optional

# In-memory OTP storage
_OTP_STORE: Dict[str, Dict] = {}

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

def is_valid_email_format(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    clean = email.strip()
    if len(clean) > 254 or len(clean) < 5:
        return False
    return bool(EMAIL_REGEX.match(clean))

# def generate_otp(length: int = 6) -> str:
#     digits = "0123456789"
#     return "".join(secrets.choice(digits) for _ in range(length))

# def store_otp(email: str, otp: str, validity_minutes: int = 10):
#     clean_email = email.strip().lower()
#     _OTP_STORE[clean_email] = {
#         "otp": otp,
#         "expires_at": datetime.now() + timedelta(minutes=validity_minutes),
#         "attempts": 0
#     }

# def verify_otp(email: str, user_otp: str) -> Tuple[bool, str]:
#     clean_email = email.strip().lower()
#     record = _OTP_STORE.get(clean_email)
    
#     if not record:
#         return False, "No OTP request found for this email. Please request a new code."
        
#     if datetime.now() > record["expires_at"]:
#         _OTP_STORE.pop(clean_email, None)
#         return False, "OTP has expired. Please request a new verification code."
        
#     if record["attempts"] >= 5:
#         _OTP_STORE.pop(clean_email, None)
#         return False, "Too many failed attempts. Please request a new OTP."
        
#     record["attempts"] += 1
    
#     if record["otp"] == user_otp.strip():
#         _OTP_STORE.pop(clean_email, None)
#         return True, "Verification successful."
        
#     return False, "Invalid verification code. Please check your email and try again."

# def send_smtp_otp_email(to_email: str, otp_code: str, user_name: Optional[str] = None) -> Tuple[bool, str]:
#     clean_email = to_email.strip().lower()
#     display_name = user_name.strip() if user_name else "Candidate"
    
#     # Store OTP in memory first
#     store_otp(clean_email, otp_code, validity_minutes=10)
    
#     # Read environment variables
#     brevo_key = os.getenv("BREVO_API_KEY")
#     resend_key = os.getenv("RESEND_API_KEY")
#     from_email = os.getenv("SMTP_FROM_EMAIL") or os.getenv("MAIL_FROM") or os.getenv("SMTP_USER") or "noreply@aicareerpro.com"
#     from_name = os.getenv("SMTP_FROM_NAME") or "AI Career Pro"

#     print(f"\n[EMAIL DISPATCH] Attempting to send OTP to: {clean_email} | Sender: {from_email}", flush=True)

#     plain_text = f"""Hello {display_name},

# Your verification code for AI Career Pro is: {otp_code}

# This code is valid for 10 minutes. If you did not request this, please ignore this email.
# """

#     html_content = f"""<!DOCTYPE html>
# <html>
# <body style="font-family: Arial, sans-serif; background: #f8fafc; padding: 20px;">
#     <div style="max-width: 500px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0;">
#         <h2 style="color: #1e293b;">⚡ AI Career Pro Verification</h2>
#         <p>Hello <strong>{display_name}</strong>,</p>
#         <p>Your account verification code is:</p>
#         <div style="background: #f1f5f9; padding: 18px; text-align: center; border-radius: 8px; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #0f172a; margin: 20px 0;">
#             {otp_code}
#         </div>
#         <p style="color: #64748b; font-size: 13px;">This code will expire in 10 minutes. Never share this code with anyone.</p>
#     </div>
# </body>
# </html>
# """

#     # =========================================================================
#     # 1. BREVO HTTPS REST API (Port 443 - Built-in urllib, zero dependencies)
#     # =========================================================================
#     if brevo_key:
#         print("[BREVO API] Found BREVO_API_KEY, sending payload via Port 443...", flush=True)
#         try:
#             url = "https://api.brevo.com/v3/smtp/email"
#             headers = {
#                 "api-key": brevo_key.strip(),
#                 "Content-Type": "application/json",
#                 "Accept": "application/json",
#                 "User-Agent": "AICareerPro-Mailer/1.0"
#             }
#             payload = {
#                 "sender": {"name": from_name, "email": from_email.strip()},
#                 "to": [{"email": clean_email, "name": display_name}],
#                 "subject": f"Your AI Career Pro Verification Code: {otp_code}",
#                 "htmlContent": html_content,
#                 "textContent": plain_text
#             }
#             req = urllib.request.Request(
#                 url, 
#                 data=json.dumps(payload).encode("utf-8"), 
#                 headers=headers, 
#                 method="POST"
#             )
#             with urllib.request.urlopen(req, timeout=12) as response:
#                 res_body = response.read().decode("utf-8")
#                 print(f"[BREVO API SUCCESS] Status: {response.status}, Body: {res_body}", flush=True)
#                 return True, "Verification code sent to your email successfully."
#         except urllib.error.HTTPError as e:
#             err_body = e.read().decode("utf-8")
#             print(f"[BREVO API HTTP ERROR] Code: {e.code}, Reason: {err_body}", flush=True)
#             # If the sender is unverified, show exact guidance
#             if "sender" in err_body.lower() or e.code in (400, 401, 403):
#                 return False, f"Brevo Error: Sender email '{from_email}' is not verified in Brevo. Set SMTP_FROM_EMAIL in Render to your Brevo registered email."
#             return False, f"Email delivery failed (Brevo API error: {e.code}). Check server logs."
#         except Exception as e:
#             print(f"[BREVO API EXCEPTION]: {e}", flush=True)

#     # =========================================================================
#     # 2. RESEND HTTPS REST API (Port 443)
#     # =========================================================================
#     if resend_key:
#         print("[RESEND API] Found RESEND_API_KEY, sending payload...", flush=True)
#         try:
#             url = "https://api.resend.com/emails"
#             headers = {
#                 "Authorization": f"Bearer {resend_key.strip()}",
#                 "Content-Type": "application/json",
#                 "User-Agent": "AICareerPro-Mailer/1.0"
#             }
#             sender = f"{from_name} <{from_email}>" if "@" in from_email else "AI Career Pro <onboarding@resend.dev>"
#             payload = {
#                 "from": sender,
#                 "to": [clean_email],
#                 "subject": f"Your Verification Code: {otp_code}",
#                 "html": html_content,
#                 "text": plain_text
#             }
#             req = urllib.request.Request(
#                 url, 
#                 data=json.dumps(payload).encode("utf-8"), 
#                 headers=headers, 
#                 method="POST"
#             )
#             with urllib.request.urlopen(req, timeout=12) as response:
#                 print(f"[RESEND SUCCESS] Status: {response.status}", flush=True)
#                 return True, "Verification code sent to your email successfully."
#         except urllib.error.HTTPError as e:
#             err_body = e.read().decode("utf-8")
#             print(f"[RESEND HTTP ERROR] Code: {e.code}, Reason: {err_body}", flush=True)
#         except Exception as e:
#             print(f"[RESEND EXCEPTION]: {e}", flush=True)

#     # =========================================================================
#     # 3. STANDARD SMTP (Local Docker fallback only)
#     # =========================================================================
#     smtp_host = os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "smtp.gmail.com"
#     smtp_port = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587")
#     smtp_user = os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME") or ""
#     smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or ""

#     if smtp_user and smtp_pass and "your_email" not in smtp_user:
#         try:
#             print(f"[SMTP] Trying SMTP connection to {smtp_host}:{smtp_port}...", flush=True)
#             msg = MIMEMultipart("alternative")
#             msg["Subject"] = f"Your Verification Code: {otp_code}"
#             msg["From"] = f"{from_name} <{from_email}>"
#             msg["To"] = clean_email
#             msg.attach(MIMEText(plain_text, "plain"))
#             msg.attach(MIMEText(html_content, "html"))

#             if smtp_port == 465:
#                 server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=8)
#             else:
#                 server = smtplib.SMTP(smtp_host, smtp_port, timeout=8)
#                 server.starttls()

#             server.login(smtp_user, smtp_pass)
#             server.sendmail(from_email, [clean_email], msg.as_string())
#             server.quit()
#             print("[SMTP SUCCESS] Email delivered via SMTP.", flush=True)
#             return True, "Verification code sent successfully."
#         except Exception as e:
#             print(f"[SMTP FAILED]: {e}", flush=True)

#     # =========================================================================
#     # 4. EXPLICIT FAILURE (Does NOT fake success)
#     # =========================================================================
#     print(f"\n==========================================", flush=True)
#     print(f"[CRITICAL ERROR] No email service was able to send the message.", flush=True)
#     print(f"Target: {clean_email} | Active OTP: {otp_code}", flush=True)
#     print(f"Make sure BREVO_API_KEY and SMTP_FROM_EMAIL are correctly set in Render.", flush=True)
#     print(f"==========================================\n", flush=True)

#     return False, "Failed to send verification email. Please check that SMTP_FROM_EMAIL matches your verified Brevo email in Render."
