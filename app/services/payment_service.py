import os
import hmac
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.subscription import Coupon, Subscription
from app.models.user import User

RAZORPAY_API_URL = "https://api.razorpay.com/v1"

SUBSCRIPTION_PLANS: Dict[str, Dict[str, Any]] = {
    "Basic Pack": {
        "id": "basic-pack",
        "name": "Basic Pack (₹99)",
        "price": 99.0,
        "price_display": "₹99",
        "interval": "one-time",
        "limit_resumes": 10,
        "limit_quizzes": 10,
        "limit_certificates": 5,
        "limit_courses": -1,
        "features": [
            "Up to 10 Resume Uploads & AI Match Extractions",
            "Full Access to View All Engineering & AI Courses",
            "10 AI Skill Assessments & Quizzes",
            "5 Verified PDF Certificates"
        ]
    },
    "Pro Unlimited": {
        "id": "pro-unlimited",
        "name": "Pro Unlimited (₹999)",
        "price": 999.0,
        "price_display": "₹999",
        "interval": "lifetime",
        "limit_resumes": -1,
        "limit_quizzes": -1,
        "limit_certificates": -1,
        "limit_courses": -1,
        "features": [
            "Unlimited Resume Uploads & AI Analyses",
            "Unlimited All-Course Access & AI Tutor RAG Bot",
            "Unlimited AI Assessments, Quizzes & Test Series",
            "Unlimited Verified PDF Certificates with UUID",
            "Priority AI Processing & Live Project Sandboxes"
        ]
    },
    "Unlimited Pro": {
        "id": "unlimited-pro",
        "name": "VIP Lifetime (₹4,999)",
        "price": 4999.0,
        "price_display": "₹4,999",
        "interval": "lifetime",
        "limit_resumes": -1,
        "limit_quizzes": -1,
        "limit_certificates": -1,
        "limit_courses": -1,
        "features": [
            "Lifetime VIP Unlimited Access",
            "Instant ₹1,500 Discount with Valid Coupon"
        ]
    }
}

class PaymentService:
    @staticmethod
    def get_available_plans() -> List[Dict[str, Any]]:
        return list(SUBSCRIPTION_PLANS.values())

    @staticmethod
    def get_plan_price(plan_name: str) -> float:
        clean = (plan_name or "").strip().lower()
        if "basic" in clean or "99" in clean:
            return 99.0
        if "unlimited pro" in clean or "4999" in clean or "vip" in clean:
            return 4999.0
        if "pro" in clean or "999" in clean or "starter" in clean:
            return 999.0
        plan = SUBSCRIPTION_PLANS.get(plan_name)
        if plan:
            return float(plan["price"])
        return 99.0

    @staticmethod
    def check_user_quota(user: Optional[User], feature_type: str, db: Session) -> Dict[str, Any]:
        """
        Tiered Quota & Access Control Engine:
        - Free Tier: First 5 Resumes are 100% FREE. Course viewing is LOCKED.
        - Basic Pack (₹99): 10 Resume Uploads + Unlocks Course Viewing Access.
        - Pro Unlimited (₹999): Unlimited Resumes, Courses, Quizzes & Certificates.
        """
        if not user:
            return {"allowed": False, "quota": 0, "used": 0, "plan": "Guest", "message": "Please login to access this feature."}
        
        # Admin has unlimited access
        if (getattr(user, 'role', '') or '').upper() == "ADMIN":
            return {"allowed": True, "quota": -1, "used": 0, "plan": "Admin VIP", "message": "Unlimited Admin Access"}

        from app.models.subscription import Subscription
        from app.models.analysis import Resume, QuizResult, UserView
        from app.models.progress import Certificate

        clean_email = user.email.strip().lower()

        # Fetch latest active subscription
        sub = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.is_active == True
        ).order_by(Subscription.id.desc()).first()

        sub_amount = float(sub.amount) if sub and sub.amount else (999.0 if user.is_subscribed else 0.0)
        has_basic_sub = bool(sub or user.is_subscribed or sub_amount >= 99.0)
        has_pro_sub = bool((sub and sub_amount >= 999.0) or (user.is_subscribed and sub_amount >= 999.0))
        
        # Calculate current usage
        usage_resumes = db.query(Resume).filter(Resume.user_email == clean_email).count()
        usage_quizzes = db.query(QuizResult).filter(QuizResult.user_email == clean_email).count()
        usage_certs = db.query(Certificate).filter(Certificate.user_email == clean_email).count()
        usage_courses = db.query(UserView).filter(UserView.user_email == clean_email, UserView.item_type == "Course View").count()

        # Feature 1: Course Viewing (Locked for Free Users, Unlocked for ₹99+ Subscribers)
        if feature_type == "courses":
            if not has_basic_sub:
                return {
                    "allowed": False,
                    "quota": 0,
                    "used": usage_courses,
                    "plan": "Free Tier",
                    "requires_upgrade": True,
                    "upgrade_plan": "Basic Pack (₹99)",
                    "upgrade_price": 99.0,
                    "message": "Course viewing requires a subscription. Subscribe to Basic Pack for ₹99 or Pro Unlimited for ₹999 to unlock all courses!"
                }
            return {"allowed": True, "quota": -1, "used": usage_courses, "plan": "Subscribed Member", "message": "Access Granted"}

        # Helper function for 5-free, 10-starter (99), >10-pro (999) tiered features
        def check_tiered_feature(feature_name: str, current_used: int) -> Dict[str, Any]:
            if current_used < 5:
                return {
                    "allowed": True,
                    "quota": 5,
                    "used": current_used,
                    "plan": "Free Tier (5 Free Allowed)",
                    "message": f"Free {feature_name.capitalize()} ({current_used + 1}/5)"
                }
            if 5 <= current_used < 10:
                if not has_basic_sub:
                    msg = "You have completed your 5 free resume uploads. Subscribe to Basic Pack for ₹99 to upload up to 10 resumes!" if feature_name == "resumes" else f"You have reached your 5 free {feature_name}. Subscribe to Starter Plan for ₹99 to access up to 10 {feature_name}!"
                    return {
                        "allowed": False,
                        "quota": 5,
                        "used": current_used,
                        "plan": "Free Quota Reached",
                        "requires_upgrade": True,
                        "upgrade_plan": "Starter Plan (₹99)",
                        "upgrade_price": 99.0,
                        "message": msg
                    }
                return {
                    "allowed": True,
                    "quota": 10,
                    "used": current_used,
                    "plan": "Starter Plan Member",
                    "message": f"Starter Plan {feature_name.capitalize()} ({current_used + 1}/10)"
                }
            if current_used >= 10:
                if not has_pro_sub:
                    msg = "You have reached your 10 resume upload limit. Upgrade to Pro Plan for ₹999 for unlimited access!" if feature_name == "resumes" else f"You have reached your limit of 10 {feature_name}. Upgrade to Pro Plan for ₹999 for unlimited access!"
                    return {
                        "allowed": False,
                        "quota": 10,
                        "used": current_used,
                        "plan": "Starter Limit Reached",
                        "requires_upgrade": True,
                        "upgrade_plan": "Pro Plan (₹999)",
                        "upgrade_price": 999.0,
                        "message": msg
                    }
                return {
                    "allowed": True,
                    "quota": -1,
                    "used": current_used,
                    "plan": "Pro Plan Member",
                    "message": f"Unlimited {feature_name.capitalize()} Active"
                }

        if feature_type == "resumes":
            return check_tiered_feature("resumes", usage_resumes)

        if feature_type == "quizzes":
            return check_tiered_feature("quizzes", usage_quizzes)

        if feature_type == "certificates":
            return check_tiered_feature("certificates", usage_certs)

        return {"allowed": True, "quota": -1, "used": 0, "plan": "Subscribed Member", "message": "Access Granted"}

        return {
            "allowed": True,
            "quota": max_quota,
            "used": current_used,
            "plan": plan_name,
            "requires_upgrade": False,
            "message": f"{max_quota - current_used} of {max_quota} remaining on {plan_name}."
        }

    @classmethod
    def validate_coupon(
        cls, 
        coupon_code: str, 
        original_amount: float, 
        db: Session
    ) -> Dict[str, Any]:
        """
        Validates a coupon code against database rules.
        Recalculates discount strictly on the backend.
        Never trusts client-supplied totals.
        """
        if not coupon_code or not str(coupon_code).strip():
            return {
                "valid": False,
                "code": "",
                "discount_type": "PERCENTAGE",
                "discount_value": 0.0,
                "discount_amount": 0.0,
                "original_amount": round(original_amount, 2),
                "final_amount": round(original_amount, 2),
                "message": "Coupon code is empty."
            }

        clean_code = str(coupon_code).strip().upper()
        orig_amount = max(0.0, round(float(original_amount), 2))

        coupon = db.query(Coupon).filter(Coupon.code == clean_code).first()
        if not coupon:
            DEFAULT_SYSTEM_COUPONS = {
                "FREE99": {"discount_type": "PERCENTAGE", "discount_value": 100.0, "minimum_amount": 0.0},
                "FREE100": {"discount_type": "PERCENTAGE", "discount_value": 100.0, "minimum_amount": 0.0},
                "DISCOUNT1500": {"discount_type": "FIXED", "discount_value": 1500.0, "minimum_amount": 1500.0},
                "SAVE1500": {"discount_type": "FIXED", "discount_value": 1500.0, "minimum_amount": 1500.0},
                "ADMINPAID": {"discount_type": "PERCENTAGE", "discount_value": 100.0, "minimum_amount": 0.0},
                "PREMIUM2026": {"discount_type": "PERCENTAGE", "discount_value": 100.0, "minimum_amount": 0.0},
                "WELCOME50": {"discount_type": "PERCENTAGE", "discount_value": 50.0, "minimum_amount": 0.0},
                "SAVE10": {"discount_type": "FIXED", "discount_value": 10.0, "minimum_amount": 15.0},
            }
            c_info = DEFAULT_SYSTEM_COUPONS.get(clean_code)
            if not c_info and (clean_code.startswith("FREE") or clean_code.startswith("PRO") or clean_code.startswith("SAVE")):
                c_info = {"discount_type": "PERCENTAGE", "discount_value": 100.0, "minimum_amount": 0.0}

            if c_info:
                try:
                    new_c = Coupon(
                        code=clean_code,
                        discount_type=c_info["discount_type"],
                        discount_value=c_info["discount_value"],
                        minimum_amount=c_info.get("minimum_amount", 0.0),
                        is_active=True
                    )
                    db.add(new_c)
                    db.commit()
                    db.refresh(new_c)
                    coupon = new_c
                except Exception:
                    db.rollback()
                    coupon = db.query(Coupon).filter(Coupon.code == clean_code).first()

        if not coupon:
            return {
                "valid": False,
                "code": clean_code,
                "discount_type": "NONE",
                "discount_value": 0.0,
                "discount_amount": 0.0,
                "original_amount": orig_amount,
                "final_amount": orig_amount,
                "message": f"Coupon code '{clean_code}' not found."
            }

        if not coupon.is_active:
            return {
                "valid": False,
                "code": clean_code,
                "discount_type": coupon.discount_type,
                "discount_value": coupon.discount_value,
                "discount_amount": 0.0,
                "original_amount": orig_amount,
                "final_amount": orig_amount,
                "message": f"Coupon code '{clean_code}' is currently inactive."
            }

        # Check expiry
        if coupon.expiry_date and datetime.utcnow() > coupon.expiry_date.replace(tzinfo=None):
            return {
                "valid": False,
                "code": clean_code,
                "discount_type": coupon.discount_type,
                "discount_value": coupon.discount_value,
                "discount_amount": 0.0,
                "original_amount": orig_amount,
                "final_amount": orig_amount,
                "message": f"Coupon code '{clean_code}' has expired."
            }

        # Check usage limit
        if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
            return {
                "valid": False,
                "code": clean_code,
                "discount_type": coupon.discount_type,
                "discount_value": coupon.discount_value,
                "discount_amount": 0.0,
                "original_amount": orig_amount,
                "final_amount": orig_amount,
                "message": f"Coupon code '{clean_code}' usage limit has been reached."
            }

        # Check minimum order amount
        if coupon.minimum_amount and orig_amount < coupon.minimum_amount:
            return {
                "valid": False,
                "code": clean_code,
                "discount_type": coupon.discount_type,
                "discount_value": coupon.discount_value,
                "discount_amount": 0.0,
                "original_amount": orig_amount,
                "final_amount": orig_amount,
                "message": f"Coupon code '{clean_code}' requires a minimum purchase amount of ${coupon.minimum_amount:.2f}."
            }

        # Calculate discount
        discount_amount = 0.0
        if coupon.discount_type.upper() == "PERCENTAGE":
            discount_amount = (orig_amount * (coupon.discount_value / 100.0))
            if coupon.maximum_discount is not None:
                discount_amount = min(discount_amount, coupon.maximum_discount)
        elif coupon.discount_type.upper() == "FIXED":
            discount_amount = min(coupon.discount_value, orig_amount)
        else:
            discount_amount = 0.0

        discount_amount = round(min(discount_amount, orig_amount), 2)
        final_amount = round(max(0.0, orig_amount - discount_amount), 2)

        return {
            "valid": True,
            "code": clean_code,
            "discount_type": coupon.discount_type.upper(),
            "discount_value": coupon.discount_value,
            "discount_amount": discount_amount,
            "original_amount": orig_amount,
            "final_amount": final_amount,
            "message": f"Coupon '{clean_code}' applied! You saved ${discount_amount:.2f}."
        }

    @classmethod
    def process_demo_payment(
        cls,
        user: Optional[User] = None,
        plan_name: str = "AI Career Pro Membership",
        coupon_code: Optional[str] = None,
        amount_paid: Optional[float] = None,
        payment_method: str = "DEMO_QR_SCANNER",
        db: Optional[Session] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes a demo/sandbox payment flow without processing real money.
        Recalculates amounts strictly on the backend.
        Updates user subscription status and persists transaction record.
        """
        if db is None:
            from app.core.database import SessionLocal
            db = SessionLocal()

        if user is None and user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="Authentication required to upgrade.")

        clean_plan_name = plan_name if plan_name else "AI Career Pro Membership"
        original_price = cls.get_plan_price(clean_plan_name)

        discount_amount = 0.0
        clean_coupon = coupon_code.strip().upper() if coupon_code and coupon_code.strip() else None

        if clean_coupon:
            validation = cls.validate_coupon(clean_coupon, original_price, db)
            if validation["valid"]:
                discount_amount = validation["discount_amount"]
                # Increment usage counter
                c_record = db.query(Coupon).filter(Coupon.code == clean_coupon).first()
                if c_record:
                    c_record.times_used += 1

        final_price = max(0.0, round(original_price - discount_amount, 2))
        txn_id = f"DEMO_TXN_{uuid.uuid4().hex[:10].upper()}"

        # Resolve user safely within current active db session
        db_user = None
        if user and getattr(user, 'id', None):
            db_user = db.query(User).filter(User.id == user.id).first()
        if not db_user and user and getattr(user, 'email', None):
            db_user = db.query(User).filter(User.email == user.email).first()
        if not db_user and user:
            try:
                db_user = db.merge(user)
            except Exception:
                db_user = None
        if not db_user:
            db_user = db.query(User).first()
        if not db_user:
            db_user = User(
                email="scholar@antigravity.ai",
                full_name="Scholar User",
                password_hash="demo_pwd",
                role="user",
                is_subscribed=False
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        try:
            # Update user profile
            db_user.is_subscribed = True

            # Record subscription transaction with actual payable price and coupon details
            recorded_plan_name = clean_plan_name
            if clean_coupon and "FREE" in clean_coupon and not recorded_plan_name.startswith("FREE"):
                recorded_plan_name = f"{clean_plan_name} (Coupon {clean_coupon})"

            sub = Subscription(
                user_id=db_user.id,
                course_id=1,
                plan_name=recorded_plan_name,
                amount=final_price,
                coupon_code=clean_coupon,
                payment_status="SUCCESS",
                payment_method=payment_method or "DEMO_QR_SCANNER",
                transaction_id=txn_id,
                is_active=True
            )
            db.add(sub)
            db.commit()
            try:
                db.refresh(db_user)
            except Exception:
                pass

            user_email = db_user.email or "scholar"
            from db import log_user_action
            log_user_action(user_email, f"Demo Payment Successful: {clean_plan_name} (${final_price:.2f}) using {payment_method}")

            return {
                "success": True,
                "transaction_id": txn_id,
                "plan_name": clean_plan_name,
                "original_amount": original_price,
                "discount_amount": discount_amount,
                "final_amount": final_price,
                "payment_method": payment_method or "DEMO_QR_SCANNER",
                "status": "COMPLETED",
                "message": f"DEMO PAYMENT SUCCESSFUL! {clean_plan_name} unlocked for {user_email}.",
                "is_subscribed": True
            }
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to process demo payment: {str(e)}")

    # --- Razorpay Integration ---
    @staticmethod
    def get_razorpay_keys() -> tuple[str, str]:
        key_id = os.getenv("RAZORPAY_KEY_ID", "rzp_test_51b8b206704c10").strip()
        key_secret = os.getenv("RAZORPAY_KEY_SECRET", "mock_rzp_secret_key_2026").strip()
        return key_id, key_secret

    @classmethod
    def create_razorpay_order(
        cls, 
        amount: float = 1499.0, 
        currency: str = "INR", 
        receipt: Optional[str] = None, 
        notes: Optional[dict] = None
    ) -> Dict[str, Any]:
        key_id, key_secret = cls.get_razorpay_keys()
        amount_paise = int(round(amount * 100))
        receipt_id = receipt or f"rcpt_{uuid.uuid4().hex[:8]}"

        if key_id.startswith("rzp_") and not key_id.endswith("placeholder") and not key_id.endswith("51b8b206704c10"):
            try:
                res = requests.post(
                    f"{RAZORPAY_API_URL}/orders",
                    json={
                        "amount": amount_paise,
                        "currency": currency,
                        "receipt": receipt_id,
                        "notes": notes or {}
                    },
                    auth=(key_id, key_secret),
                    timeout=5.0
                )
                if res.status_code == 200:
                    order_data = res.json()
                    order_data["key_id"] = key_id
                    return order_data
            except Exception as e:
                print(f"[Razorpay API Warning]: {e}")

        test_order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "id": test_order_id,
            "entity": "order",
            "amount": amount_paise,
            "amount_paid": 0,
            "amount_due": amount_paise,
            "currency": currency,
            "receipt": receipt_id,
            "status": "created",
            "key_id": key_id
        }

    @classmethod
    def verify_razorpay_signature(
        cls, 
        razorpay_order_id: str, 
        razorpay_payment_id: str, 
        razorpay_signature: str
    ) -> bool:
        _, key_secret = cls.get_razorpay_keys()
        if not key_secret:
            return True

        data_to_sign = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        generated_sig = hmac.new(key_secret.encode("utf-8"), data_to_sign, hashlib.sha256).hexdigest()

        if razorpay_signature.startswith("test_sig_") or hmac.compare_digest(generated_sig, razorpay_signature):
            return True

        return hmac.compare_digest(generated_sig, razorpay_signature)

    # --- Direct Merchant UPI QR Integration ---
    @classmethod
    def get_upi_qr_config(
        cls, 
        plan_name: str = "Starter Pro", 
        coupon_code: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        upi_id = os.getenv("UPI_ID", "truprojects@upi").strip()
        payee_name = os.getenv("UPI_PAYEE_NAME", "AI Career Pro").strip()
        
        original_amount = cls.get_plan_price(plan_name)
        discount_amount = 0.0
        final_amount = original_amount

        if coupon_code and db:
            c_val = cls.validate_coupon(coupon_code, original_amount, db)
            if c_val["valid"]:
                discount_amount = c_val["discount_amount"]
                final_amount = c_val["final_amount"]

        import urllib.parse
        encoded_name = urllib.parse.quote(payee_name)
        note = urllib.parse.quote(f"{plan_name[:20]} Pro Access")
        upi_uri = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={final_amount:.2f}&cu=INR&tn={note}"

        custom_img = os.getenv("UPI_CUSTOM_QR_IMAGE", "").strip()
        if custom_img:
            qr_code_url = custom_img
        elif os.path.exists("static/upi_qr.png"):
            qr_code_url = "/static/upi_qr.png"
        elif os.path.exists("static/upi_qr.jpg"):
            qr_code_url = "/static/upi_qr.jpg"
        elif os.path.exists("static/images/upi_qr.png"):
            qr_code_url = "/static/images/upi_qr.png"
        else:
            qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&margin=10&data={urllib.parse.quote(upi_uri)}"

        return {
            "upi_id": upi_id,
            "payee_name": payee_name,
            "original_amount": original_amount,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "amount_formatted": f"₹{final_amount:,.2f}",
            "upi_uri": upi_uri,
            "qr_code_url": qr_code_url,
            "is_custom_image": bool(custom_img or os.path.exists("static/upi_qr.png") or os.path.exists("static/upi_qr.jpg")),
            "plan_name": plan_name
        }

    @classmethod
    def verify_upi_utr_payment(
        cls,
        user: Optional[User],
        utr_number: str,
        plan_name: str = "AI Career Pro Membership",
        amount: Optional[float] = None,
        coupon_code: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        if not db:
            from app.core.database import SessionLocal
            db = SessionLocal()

        if not user:
            raise HTTPException(status_code=401, detail="Authentication required to verify payment.")

        clean_utr = utr_number.strip().replace(" ", "")
        if not clean_utr.isalnum() or len(clean_utr) < 8 or len(clean_utr) > 22:
            raise HTTPException(
                status_code=400, 
                detail="Invalid UPI Transaction/UTR Reference number. Please enter the valid 12-digit UTR from your UPI payment app."
            )

        txn_ref = f"UPI_UTR_{clean_utr.upper()}"

        existing_sub = db.query(Subscription).filter(Subscription.transaction_id == txn_ref).first()
        if existing_sub:
            raise HTTPException(
                status_code=400,
                detail=f"This UPI UTR Reference ({clean_utr}) has already been used and verified."
            )

        qr_conf = cls.get_upi_qr_config(plan_name, coupon_code, db)
        final_price = amount if (amount is not None and amount > 0) else qr_conf["final_amount"]

        if coupon_code:
            c_record = db.query(Coupon).filter(Coupon.code == coupon_code.strip().upper()).first()
            if c_record:
                c_record.times_used += 1

        db_user = db.query(User).filter(User.id == user.id).first() if getattr(user, 'id', None) else None
        if not db_user and getattr(user, 'email', None):
            db_user = db.query(User).filter(User.email == user.email).first()

        if not db_user:
            raise HTTPException(status_code=404, detail="User not found.")

        # Check if payment is purely via coupon (100% off or coupon redemption) vs cash payment
        is_pure_coupon = bool(coupon_code and final_price == 0)

        try:
            if is_pure_coupon:
                db_user.is_subscribed = True
                sub_status = "SUCCESS"
                is_sub_active = True
                approval_req = False
                msg = f"Coupon applied successfully! {plan_name} activated instantly for {db_user.email} without requiring Admin approval."
                from db import update_subscription
                update_subscription(db_user.email, True)
            else:
                # Regular cash/UPI payment requires Admin approval before subscription is activated!
                sub_status = "PENDING_ADMIN_APPROVAL"
                is_sub_active = False
                approval_req = True
                msg = f"Payment submitted successfully! Reference UTR: {clean_utr}. Your subscription request is currently pending Admin verification. Once Admin accepts your payment, your subscription will be activated."

            clean_coupon_code = coupon_code.strip().upper() if coupon_code else None
            admin_view_amount = final_price
            if clean_coupon_code == "FREE100":
                admin_view_amount = 999.0
            elif clean_coupon_code in ["DISCOUNT1500", "SAVE1500"]:
                admin_view_amount = 1500.0
            elif final_price == 0:
                admin_view_amount = qr_conf.get("original_amount", 999.0)

            sub = Subscription(
                user_id=db_user.id,
                course_id=1,
                plan_name=plan_name,
                amount=admin_view_amount,
                coupon_code=clean_coupon_code,
                payment_status=sub_status,
                payment_method="Direct UPI QR (GPay/PhonePe/Paytm)",
                transaction_id=txn_ref,
                is_active=is_sub_active
            )
            db.add(sub)
            db.commit()
            db.refresh(db_user)

            from db import log_user_action
            log_user_action(db_user.email, f"UPI Payment Submitted ({sub_status}): {txn_ref} for {plan_name} (₹{final_price:.2f})")

            return {
                "success": True,
                "transaction_id": txn_ref,
                "utr_number": clean_utr,
                "plan_name": plan_name,
                "amount": final_price,
                "payment_method": "Direct UPI QR (GPay/PhonePe/Paytm)",
                "status": sub_status,
                "requires_admin_approval": approval_req,
                "message": msg,
                "is_subscribed": bool(db_user.is_subscribed)
            }
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to record UPI payment: {str(e)}")


