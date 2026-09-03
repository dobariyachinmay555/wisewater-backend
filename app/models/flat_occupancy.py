from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class FlatOccupancyHistory(Base):
    __tablename__ = "flat_occupancy_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False, index=True)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True, index=True)
    flat_number = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(50), default="PRIMARY_RESIDENT")
    start_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_date = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True, index=True)
    start_meter_reading = Column(Integer, default=0)
    end_meter_reading = Column(Integer, nullable=True)
    move_out_reason = Column(String(255), nullable=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    society = relationship("Society")
    block = relationship("Block")
    user = relationship("User", foreign_keys=[user_id])
    meter = relationship("Meter")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])
