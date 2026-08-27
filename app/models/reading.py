from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base

class MeterReading(Base):
    __tablename__ = "meter_readings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True)
    previous_unit = Column(Integer, nullable=False, default=0)
    current_unit = Column(Integer, nullable=False)
    total_unit = Column(Integer, nullable=False)  # current_unit - previous_unit
    unit_price = Column(Numeric(10, 2), nullable=False, default=25.00)
    total_price = Column(Numeric(10, 2), nullable=False)  # total_unit * unit_price
    image_url = Column(Text, nullable=True)
    status = Column(Integer, default=0, nullable=False)  # 0: Pending, 1: Approved, 2: Rejected, 3: Flagged
    remarks = Column(Text, nullable=True)
    is_deletable = Column(Boolean, default=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="readings")
    user = relationship("User", back_populates="readings", foreign_keys=[user_id])
    block = relationship("Block")
    meter = relationship("Meter", back_populates="readings")
