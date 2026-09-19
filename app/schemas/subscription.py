from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class SubscriptionCreate(BaseModel):
    course_id: Optional[int] = None
    plan_name: Optional[str] = "AI Career Pro Membership"
    transaction_id: Optional[str] = "mock_transaction_123"

class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int] = None
    plan_name: Optional[str] = "AI Career Pro Membership"
    amount: Optional[float] = 0.0
    coupon_code: Optional[str] = None
    payment_status: str
    payment_method: Optional[str] = "DEMO_PAYMENT"
    is_active: bool
    enrolled_at: datetime

    class Config:
        from_attributes = True

# --- Coupon Schemas ---
class CouponValidateRequest(BaseModel):
    code: Optional[str] = None
    coupon_code: Optional[str] = None
    plan_name: Optional[str] = "AI Career Pro Membership"
    amount: Optional[float] = None
    original_amount: Optional[float] = 19.99

    def get_code(self) -> str:
        return (self.code or self.coupon_code or "").strip()

    def get_amount(self) -> float:
        if self.amount is not None:
            return float(self.amount)
        if self.original_amount is not None:
            return float(self.original_amount)
        return 19.99

class CouponValidateResponse(BaseModel):
    valid: bool
    code: str
    coupon_code: Optional[str] = None
    discount_type: str
    discount_value: float
    discount_amount: float
    original_amount: float
    final_amount: float
    message: str

# --- Demo Payment Schemas ---
class DemoPaymentRequest(BaseModel):
    plan_name: str = "AI Career Pro Membership"
    coupon_code: Optional[str] = None
    payment_method: str = "DEMO_QR_SCANNER" # DEMO_QR_SCANNER, DEMO_CARD, DEMO_UPI
    amount_paid: Optional[float] = None

class DemoPaymentResponse(BaseModel):
    success: bool
    transaction_id: str
    plan_name: str
    original_amount: float
    discount_amount: float
    final_amount: float
    payment_method: str
    status: str
    message: str
    is_subscribed: bool

class PlanInfo(BaseModel):
    id: str
    name: str
    price: float
    price_display: str
    interval: str
    features: List[str]

