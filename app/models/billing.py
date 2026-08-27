import uuid
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, ForeignKey, JSON
from app.core.database import Base

class Bill(Base):
    __tablename__ = "bills"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_number = Column(String(100), unique=True, nullable=False, index=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reading_id = Column(Integer, ForeignKey("meter_readings.id", ondelete="SET NULL"), nullable=True)
    billing_month = Column(Integer, nullable=False)
    billing_year = Column(Integer, nullable=False)
    consumption_units = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    due_date = Column(Date, default=lambda: date.today())
    payment_status = Column(String(50), default="PENDING")  # GENERATED, PENDING, PAID, OVERDUE, CANCELLED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    gateway = Column(String(50), default="RAZORPAY")
    transaction_id = Column(String(255), unique=True, nullable=True)
    gateway_order_id = Column(String(255), nullable=True)
    gateway_payment_id = Column(String(255), nullable=True)
    gateway_signature = Column(String(255), nullable=True)
    status = Column(String(50), default="PENDING")  # PENDING, SUCCESS, FAILED, REFUNDED
    raw_response = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
