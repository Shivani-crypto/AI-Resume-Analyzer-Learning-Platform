from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..core.database import get_db
from ..models.user import User
from ..models.course import Course
from ..models.subscription import Subscription
from ..schemas.subscription import (
    SubscriptionCreate, SubscriptionResponse,
    CouponValidateRequest, CouponValidateResponse,
    DemoPaymentRequest, DemoPaymentResponse, PlanInfo
)
from .auth import get_current_user, get_current_user_optional
from ..services.payment_service import PaymentService
from db import update_subscription, log_user_action

router = APIRouter()

# --- Plans & Catalog ---
@router.get("/plans", response_model=List[PlanInfo])
def get_plans():
    """Returns available subscription tiers."""
    return PaymentService.get_available_plans()

# --- Coupon Validation ---
@router.post("/coupons/validate", response_model=CouponValidateResponse)
def validate_coupon_endpoint(
    req: CouponValidateRequest,
    db: Session = Depends(get_db)
):
    """
    Validates a coupon code against database rules.
    Recalculates discounts on the backend.
    """
    code = req.get_code()
    orig_amount = req.get_amount()
    if orig_amount <= 0:
        orig_amount = PaymentService.get_plan_price(req.plan_name or "")
    result = PaymentService.validate_coupon(
        coupon_code=code,
        original_amount=orig_amount,
        db=db
    )
    result["coupon_code"] = result.get("code")
    return result

# --- Demo / Development Payment Scanner ---
@router.post("/demo-payment", response_model=DemoPaymentResponse)
def process_demo_payment_endpoint(
    req: DemoPaymentRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Demo Payment Simulator for development and demonstration.
    Does NOT process real money. Recalculates final payable amount on backend.
    """
    if not current_user:
        # Fallback to test user if in demo mode
        current_user = db.query(User).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required to upgrade.")

    return PaymentService.process_demo_payment(
        user=current_user,
        plan_name=req.plan_name,
        coupon_code=req.coupon_code,
        amount_paid=req.amount_paid,
        payment_method=req.payment_method,
        db=db
    )

# --- Course Subscriptions & Enrollment ---
@router.post("/enroll", response_model=SubscriptionResponse)
def enroll_in_course(
    sub_in: SubscriptionCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Enrolls a student in a course. 
    """
    if sub_in.course_id:
        course = db.query(Course).filter(Course.id == sub_in.course_id).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        existing = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.course_id == sub_in.course_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Already enrolled in this course")

    db_sub = Subscription(
        user_id=current_user.id,
        course_id=sub_in.course_id,
        plan_name=sub_in.plan_name or "AI Career Pro Membership",
        payment_status="SUCCESS",
        payment_method="DEMO_PAYMENT",
        transaction_id=sub_in.transaction_id,
        is_active=True
    )
    
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    
    return db_sub

@router.get("/my-courses", response_model=List[SubscriptionResponse])
def get_my_courses(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Returns all active subscriptions for the logged-in student.
    """
    subs = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.is_active == True
    ).all()
    return subs

# --- Official Razorpay Payment Gateway Endpoints ---
class RazorpayOrderRequest(BaseModel):
    amount: float = 999.0
    currency: str = "INR"
    plan_name: str = "Starter Pro"

class RazorpayVerifyRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    plan_name: Optional[str] = "Starter Pro"
    amount: Optional[float] = 999.0

@router.get("/razorpay/config")
def get_razorpay_config():
    key_id, _ = PaymentService.get_razorpay_keys()
    return {
        "key_id": key_id,
        "currency": "INR",
        "amount": 99900,
        "amount_display": "₹999",
        "plan_name": "Starter Pro"
    }

@router.post("/razorpay/create-order")
def create_razorpay_order_endpoint(
    req: RazorpayOrderRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    notes = {
        "plan": req.plan_name,
        "user_email": current_user.email if current_user else "guest@example.com"
    }
    order = PaymentService.create_razorpay_order(
        amount=req.amount,
        currency=req.currency,
        notes=notes
    )
    return order

@router.post("/razorpay/verify-payment")
def verify_razorpay_payment_endpoint(
    req: RazorpayVerifyRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    is_valid = PaymentService.verify_razorpay_signature(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Razorpay signature verification failed. Invalid transaction.")

    if current_user:
        sub_record = Subscription(
            user_id=current_user.id,
            plan_name=req.plan_name or "Starter Pro",
            amount=req.amount or 999.0,
            payment_status="PENDING_ADMIN_APPROVAL",
            payment_method="Razorpay (UPI/Cards)",
            transaction_id=req.razorpay_payment_id,
            is_active=False
        )
        db.add(sub_record)
        db.commit()
        log_user_action(current_user.email, f"Razorpay payment verified & pending Admin approval: {req.razorpay_payment_id} for {req.plan_name} (₹{req.amount})")

    return {
        "success": True,
        "transaction_id": req.razorpay_payment_id,
        "order_id": req.razorpay_order_id,
        "amount": req.amount,
        "status": "PENDING_ADMIN_APPROVAL",
        "requires_admin_approval": True,
        "payment_method": "Razorpay Official Gateway (UPI/Card/NetBanking)",
        "message": f"Razorpay payment received! Your {req.plan_name} subscription request is submitted for Admin Approval. Access will unlock once Admin accepts your payment."
    }

# --- Direct Merchant UPI QR Endpoints ---
class UPIQRVerifyRequest(BaseModel):
    utr_number: str
    plan_name: Optional[str] = "Starter Pro"
    amount: Optional[float] = None
    coupon_code: Optional[str] = None

@router.get("/upi-qr-config")
def get_upi_qr_config_endpoint(
    plan_name: Optional[str] = "Starter Pro",
    coupon_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Returns dynamic UPI QR payload and image URL."""
    return PaymentService.get_upi_qr_config(plan_name=plan_name, coupon_code=coupon_code, db=db)

@router.post("/verify-upi-payment")
def verify_upi_payment_endpoint(
    req: UPIQRVerifyRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Verifies submitted 12-digit UPI UTR reference and handles admin approval requirements."""
    if not current_user:
        current_user = db.query(User).first()
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required to verify payment.")
            
    return PaymentService.verify_upi_utr_payment(
        user=current_user,
        utr_number=req.utr_number,
        plan_name=req.plan_name or "Starter Pro",
        amount=req.amount,
        coupon_code=req.coupon_code,
        db=db
    )

# --- Admin Subscription Pending Approvals ---
@router.get("/admin/pending-approvals")
def get_pending_subscriptions_endpoint(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Returns list of all pending subscriptions awaiting Admin acceptance."""
    pending = db.query(Subscription).filter(
        Subscription.payment_status == "PENDING_ADMIN_APPROVAL"
    ).order_by(Subscription.id.desc()).all()

    res = []
    for s in pending:
        u = db.query(User).filter(User.id == s.user_id).first()
        res.append({
            "id": s.id,
            "user_id": s.user_id,
            "user_email": u.email if u else "Unknown",
            "user_name": u.full_name if u else "Unknown",
            "plan_name": s.plan_name,
            "amount": s.amount,
            "coupon_code": s.coupon_code,
            "payment_method": s.payment_method,
            "transaction_id": s.transaction_id,
            "payment_status": s.payment_status,
            "enrolled_at": s.enrolled_at.isoformat() if s.enrolled_at else None
        })
    return res

class AdminApproveSubscriptionRequest(BaseModel):
    subscription_id: int
    action: str = "approve"

@router.post("/admin/approve-pending")
def approve_pending_subscription_endpoint(
    req: AdminApproveSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Approve or reject a pending subscription request."""
    sub = db.query(Subscription).filter(Subscription.id == req.subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription record not found.")

    u = db.query(User).filter(User.id == sub.user_id).first()

    if req.action.lower() == "approve":
        sub.payment_status = "SUCCESS"
        sub.is_active = True
        if u:
            u.is_subscribed = True
            update_subscription(u.email, True)
            admin_email = current_user.email if current_user else "Admin"
            log_user_action(admin_email, f"Admin APPROVED subscription #{sub.id} for {u.email} ({sub.plan_name})")
        db.commit()
        return {"success": True, "message": f"Subscription APPROVED and activated for {u.email if u else 'user'}!"}
    else:
        sub.payment_status = "REJECTED"
        sub.is_active = False
        db.commit()
        if u:
            admin_email = current_user.email if current_user else "Admin"
            log_user_action(admin_email, f"Admin REJECTED subscription #{sub.id} for {u.email}")
        return {"success": True, "message": "Subscription request rejected."}



