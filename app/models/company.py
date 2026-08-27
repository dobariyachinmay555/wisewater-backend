import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Integer, JSON
from app.core.database import Base

class CompanyStaff(Base):
    __tablename__ = "company_staff"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="ADMIN")  # OWNER, SUPER_ADMIN, ADMIN, SUPPORT, FINANCE, READ_ONLY
    is_active = Column(Boolean, default=True)
    two_factor_enabled = Column(Boolean, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    plan_type = Column(String(50), nullable=False, default="MONTHLY")  # TRIAL, MONTHLY, ANNUAL, CUSTOM
    price_per_flat = Column(Numeric(10, 2), default=15.00)
    base_price = Column(Numeric(10, 2), default=500.00)
    max_flats = Column(Integer, default=500)
    features = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
