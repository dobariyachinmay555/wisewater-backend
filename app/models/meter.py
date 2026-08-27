from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Meter(Base):
    __tablename__ = "meters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    flat_number = Column(String(50), nullable=False)
    meter_serial_number = Column(String(100), unique=True, nullable=False)
    initial_reading = Column(Integer, default=0)
    current_reading = Column(Integer, default=0)
    status = Column(String(50), default="ACTIVE")  # ACTIVE, INACTIVE, DAMAGED, REPLACED, UNASSIGNED
    installed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="meters")
    block = relationship("Block", back_populates="meters")
    user = relationship("User", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter")
