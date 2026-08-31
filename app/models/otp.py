from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base

class OtpVerification(Base):
    __tablename__ = "otp_verifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mobile_number = Column(String(20), nullable=False, index=True)
    otp_code = Column(String(128), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
