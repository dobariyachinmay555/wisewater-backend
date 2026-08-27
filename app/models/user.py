from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    mobile_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    user_type = Column(Integer, default=1, nullable=False)  # 1: Member, 2: Committee Admin, 3: Chairman
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="SET NULL"), nullable=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True)
    flat_number = Column(String(50), nullable=True)
    approval_status = Column(Integer, default=1, nullable=False)  # 0: Pending, 1: Approved, 2: Rejected
    previous_unit = Column(Integer, default=100)
    fcm_token = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="users")
    block = relationship("Block", back_populates="users")
    readings = relationship("MeterReading", back_populates="user", foreign_keys="[MeterReading.user_id]")
    meters = relationship("Meter", back_populates="user")
