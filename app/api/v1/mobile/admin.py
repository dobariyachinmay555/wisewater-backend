from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.models.society import Society, Block
from app.models.reading import MeterReading
from app.schemas.mobile import (
    MobileApiResponse, UpdateUnitPriceRequest, UpdatePendingRequestStatus, UpdateReadingRequestStatus
)
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details
from app.services.billing_service import generate_bill_for_reading

router = APIRouter()

@router.post("/update-unit-price", response_model=MobileApiResponse)
def update_unit_price(
    payload: UpdateUnitPriceRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Update water price per unit for the society (Chairman only)."""
    try:
        new_price = float(payload.unit_price.strip())
    except ValueError:
        return MobileApiResponse(status=0, message="Invalid unit price", data={})
        
    soc_id = current_user.society_id or 1
    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})
        
    society.unit_price = new_price
    db.commit()
    return MobileApiResponse(status=1, message="Unit price updated successfully", data={})

@router.get("/pending-requests", response_model=MobileApiResponse)
def get_pending_requests(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get pending resident join requests for society admin review."""
    soc_id = current_user.society_id or 1
    pending_users = db.query(User).filter(
        User.society_id == soc_id,
        User.approval_status == 0
    ).all()
    
    result = [format_user_details(u) for u in pending_users]
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/pending-requests/update-status", response_model=MobileApiResponse)
def update_pending_request_status(
    payload: UpdatePendingRequestStatus,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Approve or reject a resident join request."""
    user = db.query(User).filter(User.id == payload.apartment_user_id).first()
    if not user:
        return MobileApiResponse(status=0, message="User not found", data={})
        
    user.approval_status = payload.status  # 1: Approved, 2: Rejected
    if payload.previous_unit and payload.previous_unit.strip():
        try:
            user.previous_unit = int(payload.previous_unit.strip())
        except ValueError:
            pass

    if payload.status == 1:
        for r in user.readings:
            if r.status == 0 and "Initial" in (r.remarks or ""):
                r.status = 1
                r.remarks = "Approved Baseline Reading"

    db.commit()
    msg = "Request accepted successfully" if payload.status == 1 else "Request rejected successfully"
    return MobileApiResponse(status=1, message=msg, data={})

@router.get("/pending-unit-reading-requests", response_model=MobileApiResponse)
def get_pending_reading_requests(
    block_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get pending meter readings submitted by residents."""
    soc_id = current_user.society_id or 1
    query = db.query(MeterReading).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 0  # Pending
    )
    if block_id is not None and block_id > 0:
        query = query.filter(MeterReading.block_id == block_id)
        
    readings = query.order_by(MeterReading.created_at.desc()).all()
    result = []
    for r in readings:
        user = db.query(User).filter(User.id == r.user_id).first()
        user_data = format_user_details(user) if user else None
        
        img_url = r.image_url or ""
        if img_url and not (img_url.startswith("http://") or img_url.startswith("https://")):
            img_url = f"http://127.0.0.1:8000{img_url if img_url.startswith('/') else '/' + img_url}"

        result.append({
            "user_unit_history_id": r.id,
            "previous_unit": r.previous_unit,
            "current_unit": r.current_unit,
            "total_unit": r.total_unit,
            "unit_price": float(r.unit_price),
            "image": img_url,
            "status": r.status,
            "created_at": r.created_at.strftime("%d %b %Y") if r.created_at else "",
            "user_details": user_data
        })
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/pending-unit-reading-requests/update-status", response_model=MobileApiResponse)
def update_pending_reading_status(
    payload: UpdateReadingRequestStatus,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Approve or reject a submitted meter reading."""
    reading = db.query(MeterReading).filter(MeterReading.id == payload.user_unit_history_id).first()
    if not reading:
        return MobileApiResponse(status=0, message="Reading not found", data={})
        
    reading.status = payload.status  # 1: Approved, 2: Rejected
    reading.approved_by_user_id = current_user.id
    reading.approved_at = datetime.now(timezone.utc)
    
    if payload.status == 1:
        # Update user's previous baseline reading and generate bill
        user = db.query(User).filter(User.id == reading.user_id).first()
        if user:
            user.previous_unit = reading.current_unit
        generate_bill_for_reading(db, reading)
        
    db.commit()
    msg = "Request accepted successfully" if payload.status == 1 else "Request rejected successfully"
    return MobileApiResponse(status=1, message=msg, data={})
