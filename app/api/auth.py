from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from typing import Optional
from pydantic import BaseModel

from ..core.database import get_db
from ..core.security import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
from ..models.user import User
from ..schemas.user import UserCreate, UserResponse, Token

class SubscriptionRequest(BaseModel):
    coupon_code: str

router = APIRouter()
security_bearer = HTTPBearer(auto_error=False)

def get_current_user(
    request: Request,
    auth_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = None
    if auth_creds and auth_creds.credentials and auth_creds.credentials.strip() not in ("", "null", "undefined"):
        token = auth_creds.credentials.strip()
    if not token:
        cookie_tok = request.cookies.get("access_token")
        if cookie_tok and cookie_tok.strip() not in ("", "null", "undefined"):
            token = cookie_tok.strip()
    if not token:
        auth_hdr = request.headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            raw_tok = auth_hdr[7:].strip()
            if raw_tok not in ("", "null", "undefined"):
                token = raw_tok

    if not token or token in ("", "null", "undefined"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authorization token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None or str(email).strip() in ("", "null", "undefined"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing sub (email)",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"JWT validation error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_email = str(email).strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User '{clean_email}' not found in database",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")

    return user

def get_current_user_optional(
    request: Request,
    auth_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> Optional[User]:
    try:
        return get_current_user(request, auth_creds, db)
    except Exception:
        return None

def get_current_active_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.upper() != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin authorization required")
    return current_user

class SendOTPRequest(BaseModel):
    email: str
    full_name: Optional[str] = None

class RegisterWithOTPRequest(BaseModel):
    full_name: str
    email: str
    ph_number: Optional[str] = None
    password: str
    otp: str
    preferred_language: Optional[str] = "English"

@router.post("/send-otp")
def api_send_otp(req: SendOTPRequest, db: Session = Depends(get_db)):
    from app.services.email_service import is_valid_email_format, generate_otp, send_smtp_otp_email
    
    clean_email = req.email.strip().lower()
    if not is_valid_email_format(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email format. Please provide a valid email address.")
        
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="This email is already registered. Please log in.")
        
    otp = generate_otp(6)
    success, msg = send_smtp_otp_email(clean_email, otp, req.full_name)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "message": msg}

@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    clean_email = user_in.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=clean_email,
        full_name=user_in.full_name.strip(),
        hashed_password=hashed_password,
        preferred_language=user_in.preferred_language or "English",
        role="STUDENT"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/register-with-otp", response_model=UserResponse)
def register_with_otp(req: RegisterWithOTPRequest, db: Session = Depends(get_db)):
    from app.services.email_service import is_valid_email_format, verify_otp
    
    clean_email = req.email.strip().lower()
    if not is_valid_email_format(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email address.")
        
    user = db.query(User).filter(User.email == clean_email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered. Please login.")
        
    is_valid, msg = verify_otp(clean_email, req.otp)
    if not is_valid:
        raise HTTPException(status_code=400, detail=msg)
        
    hashed_password = get_password_hash(req.password)
    db_user = User(
        email=clean_email,
        full_name=req.full_name.strip(),
        ph_number=req.ph_number.strip() if req.ph_number else None,
        hashed_password=hashed_password,
        preferred_language=req.preferred_language or "English",
        role="STUDENT"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    clean_email = form_data.username.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(subject=user.email)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/subscribe")
def process_subscription(req: SubscriptionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import uuid
    code = (req.coupon_code or "").strip().upper()
    if code in ["FREE100", "PREMIUM2026", "DISCOUNT1500", "SAVE1500"]:
        current_user.is_subscribed = True
        
        view_amt = 999.0 if code in ["FREE100", "PREMIUM2026"] else 1500.0
        from app.models.subscription import Subscription
        sub = Subscription(
            user_id=current_user.id,
            course_id=1,
            plan_name="AI Career Pro Membership",
            amount=view_amt,
            coupon_code=code,
            payment_status="SUCCESS",
            payment_method="COUPON",
            transaction_id=f"CPN_{uuid.uuid4().hex[:8].upper()}",
            is_active=True
        )
        db.add(sub)
        db.commit()
        return {"success": True, "message": "Subscription activated successfully!"}
    
    raise HTTPException(status_code=400, detail="Invalid coupon code or payment failed.")
