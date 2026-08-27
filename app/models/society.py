from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Society(Base):
    __tablename__ = "societies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=False)
    zip_code = Column(String(20), nullable=False)
    unit_price = Column(Numeric(10, 2), default=25.00)
    status = Column(String(50), default="ACTIVE")  # PENDING, ACTIVE, SUSPENDED, ARCHIVED
    subscription_status = Column(String(50), default="ACTIVE")  # TRIAL, ACTIVE, PAST_DUE, SUSPENDED, CANCELLED, EXPIRED
    subscription_plan_id = Column(String(36), ForeignKey("subscription_plans.id"), nullable=True)
    subscription_start_date = Column(DateTime, nullable=True)
    subscription_renewal_date = Column(DateTime, nullable=True)
    chairman_name = Column(String(255), nullable=True)
    chairman_mobile = Column(String(20), nullable=True)
    chairman_email = Column(String(255), nullable=True)
    property_category = Column(String(50), default="FLAT_APARTMENT")  # FLAT_APARTMENT, ROW_HOUSE
    total_houses = Column(Integer, nullable=True)
    registration_id = Column(String(50), unique=True, nullable=True, index=True)
    rejection_reason = Column(Text, nullable=True)
    change_request_notes = Column(Text, nullable=True)
    contact_number = Column(String(20), nullable=True)
    society_email = Column(String(255), nullable=True)
    establishment_year = Column(Integer, nullable=True)
    photo_submission_frequency = Column(String(50), default="1_MONTH")  # 1_MONTH, 6_MONTHS
    registration_status = Column(String(50), default="ACTIVE")  # DRAFT, PENDING, UNDER_REVIEW, CHANGES_REQUIRED, ACTIVE, REJECTED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    blocks = relationship("Block", back_populates="society", cascade="all, delete-orphan")
    flats = relationship("Flat", back_populates="society", cascade="all, delete-orphan")
    houses = relationship("House", back_populates="society", cascade="all, delete-orphan")
    users = relationship("User", back_populates="society")
    meters = relationship("Meter", back_populates="society")
    readings = relationship("MeterReading", back_populates="society")

class Block(Base):
    __tablename__ = "blocks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(100), nullable=False)
    total_flats = Column(Integer, default=20)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="blocks")
    flats = relationship("Flat", back_populates="block", cascade="all, delete-orphan")
    users = relationship("User", back_populates="block")
    meters = relationship("Meter", back_populates="block")

class Flat(Base):
    __tablename__ = "flats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    block_id = Column(Integer, ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False)
    flat_number = Column(String(50), nullable=False)
    status = Column(String(50), default="VACANT")  # VACANT, OCCUPIED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="flats")
    block = relationship("Block", back_populates="flats")

class House(Base):
    __tablename__ = "houses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    society_id = Column(Integer, ForeignKey("societies.id", ondelete="CASCADE"), nullable=False)
    house_number = Column(String(50), nullable=False)
    status = Column(String(50), default="VACANT")  # VACANT, OCCUPIED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    society = relationship("Society", back_populates="houses")

