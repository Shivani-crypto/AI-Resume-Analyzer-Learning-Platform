from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    discount_type = Column(String, default="PERCENTAGE") # PERCENTAGE, FIXED
    discount_value = Column(Float, nullable=False) # e.g. 50.0 for 50%, or 10.0 for $10
    minimum_amount = Column(Float, default=0.0) # minimum order amount required
    maximum_discount = Column(Float, nullable=True) # maximum discount cap for percentage
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True) # None = unlimited
    times_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True) # nullable for site-wide Pro membership
    plan_name = Column(String, default="AI Career Pro Membership")
    amount = Column(Float, default=0.0)
    coupon_code = Column(String, nullable=True)
    
    # Payment Tracking (Razorpay / Stripe / Demo Scanner)
    payment_status = Column(String, default="PENDING") # PENDING, SUCCESS, FAILED
    payment_method = Column(String, default="DEMO_PAYMENT") # DEMO_PAYMENT, RAZORPAY, STRIPE, COUPON
    transaction_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")
    course = relationship("Course")

