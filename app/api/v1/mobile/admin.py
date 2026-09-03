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

    # Send push notification to resident
    try:
        from app.services.notification_service import send_user_notification
        soc_name = user.society.name if user.society else "the society"
        if payload.status == 1:
            send_user_notification(
                db=db,
                user_id=user.id,
                title="Society Member Approved! 🎉",
                message=f"Chairman successfully approved your member request for Flat/House {user.flat_number or ''} in {soc_name}.",
                notification_type="JOIN_APPROVED",
                data={"status": "APPROVED", "society_id": str(user.society_id or "")},
                sender_id=current_user.id
            )
        else:
            send_user_notification(
                db=db,
                user_id=user.id,
                title="Society Join Request Update",
                message=f"Your request to join {soc_name} was not approved by the Society Chairman.",
                notification_type="JOIN_REJECTED",
                data={"status": "REJECTED"},
                sender_id=current_user.id
            )
    except Exception as e:
        pass


    msg = "Request accepted successfully" if payload.status == 1 else "Request rejected successfully"
    return MobileApiResponse(status=1, message=msg, data={})

from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details, resolve_media_url

@router.get("/pending-unit-reading-requests", response_model=MobileApiResponse)
def get_pending_reading_requests(
    block_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get pending meter readings submitted by residents."""
    soc_id = current_user.society_id or 1
    query = db.query(MeterReading).join(User, MeterReading.user_id == User.id).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 0,  # Pending
        User.approval_status == 1  # Only show reading requests for approved members!
    )
    if block_id is not None and block_id > 0:
        query = query.filter(MeterReading.block_id == block_id)
        
    readings = query.order_by(MeterReading.created_at.desc()).all()
    result = []
    for r in readings:
        user = db.query(User).filter(User.id == r.user_id).first()
        user_data = format_user_details(user) if user else None
        
        result.append({
            "user_unit_history_id": r.id,
            "previous_unit": r.previous_unit,
            "current_unit": r.current_unit,
            "total_unit": r.total_unit,
            "unit_price": float(r.unit_price),
            "image": resolve_media_url(r.image_url),
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
    
    bill = None
    if payload.status == 1:
        # Update user's previous baseline reading and generate bill
        user = db.query(User).filter(User.id == reading.user_id).first()
        if user:
            user.previous_unit = reading.current_unit
            if user.flat_number and user.society_id:
                from app.models.meter import Meter
                meter = db.query(Meter).filter(
                    Meter.society_id == user.society_id,
                    Meter.block_id == user.block_id,
                    Meter.flat_number == user.flat_number
                ).first()
                if meter:
                    meter.current_reading = reading.current_unit
        bill = generate_bill_for_reading(db, reading)
        
    db.commit()

    # Send push notification to resident
    try:
        from app.services.notification_service import send_user_notification
        if payload.status == 1:
            amount_str = f"₹{reading.total_price:.2f}" if reading.total_price else "₹0.00"
            send_user_notification(
                db=db,
                user_id=reading.user_id,
                title="Meter Reading Approved 💧",
                message=f"Chairman successfully approved your meter reading of {reading.current_unit} units ({reading.total_unit} units consumed). Bill: {amount_str}.",
                notification_type="READING_APPROVED",
                data={
                    "reading_id": str(reading.id),
                    "bill_id": str(bill.id) if bill else "",
                    "status": "APPROVED"
                },
                sender_id=current_user.id
            )
        else:
            send_user_notification(
                db=db,
                user_id=reading.user_id,
                title="Meter Reading Rejected",
                message="Your submitted meter reading was rejected by the Society Chairman. Please verify and submit a new reading.",
                notification_type="READING_REJECTED",
                data={"reading_id": str(reading.id), "status": "REJECTED"},
                sender_id=current_user.id
            )
    except Exception as e:
        pass


    msg = "Request accepted successfully" if payload.status == 1 else "Request rejected successfully"
    return MobileApiResponse(status=1, message=msg, data={})
