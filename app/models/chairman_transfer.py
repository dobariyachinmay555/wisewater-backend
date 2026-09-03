import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class ChairmanTransfer(Base):
    __tablename__ = "chairman_transfers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_mobile_number = Column(String(20), nullable=False, index=True)
    to_name = Column(String(255), nullable=False)
    to_email = Column(String(255), nullable=True)
    otp_code = Column(String(128), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    # Statuses: PENDING_OTP, OTP_VERIFIED, COMPLETED, CANCELLED, EXPIRED
    status = Column(String(50), default="PENDING_OTP", nullable=False, index=True)
    demote_old_to_resident = Column(Boolean, default=True)
    cancellation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    society = relationship("Society")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
