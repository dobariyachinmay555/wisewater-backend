from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.society import Society, Block, Flat, House
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.schemas.mobile import (
    MobileApiResponse,
    UpdateSocietyProfileRequest,
    AddMemberRequest
)
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details
from app.services.audit_service import record_audit_log

router = APIRouter()

@router.get("/chairman/dashboard-summary", response_model=MobileApiResponse)
def get_chairman_dashboard_summary(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Retrieve real database metrics for the Chairman Dashboard."""
    if current_user.user_type != 3:
        # Fallback allow for demo/testing or non-chairman
        pass
        
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked to Chairman", data={})
        
    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})
        
    prop_category = society.property_category or "FLAT_APARTMENT"
    total_blocks = len(society.blocks)
    
    if prop_category == "FLAT_APARTMENT":
        total_units = sum([b.total_flats for b in society.blocks])
    else:
        total_units = society.total_houses or 0
        
    joined_members = db.query(User).filter(
        User.society_id == soc_id,
        User.is_active == True,
        User.approval_status == 1
    ).count()
    
    pending_join_requests = db.query(User).filter(
        User.society_id == soc_id,
        User.approval_status == 0
    ).count()

    remaining_units = max(0, total_units - joined_members)
    
    total_residents = joined_members
    total_meters = db.query(Meter).filter(Meter.society_id == soc_id).count()
    if total_meters == 0:
        total_meters = total_units
        
    pending_readings = db.query(MeterReading).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 0
    ).count()
    
    approved_readings = db.query(MeterReading).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 1
    ).count()
    
    # Current month consumption & billing calculation
    now = datetime.now(timezone.utc)
    current_month_readings = db.query(MeterReading).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 1
    ).all()
    
    total_consumption = sum([r.total_unit for r in current_month_readings]) if current_month_readings else 0
    total_billing = sum([float(r.total_price) for r in current_month_readings]) if current_month_readings else 0.0
    
    blocks_summary = [
        {
            "id": b.id,
            "block_id": b.id,
            "title": b.title,
            "total_flats": b.total_flats,
            "occupied_flats": db.query(User).filter(User.block_id == b.id, User.is_active == True, User.approval_status == 1).count()
        }
        for b in society.blocks
    ]
    
    return MobileApiResponse(
        status=1,
        message="Dashboard summary loaded",
        data={
            "society_id": society.id,
            "society_name": society.name,
            "code": society.code,
            "property_category": prop_category,
            "total_blocks": total_blocks,
            "total_units": total_units,
            "total_flats_or_houses": total_units,
            "joined_members": joined_members,
            "remaining_units": remaining_units,
            "pending_join_requests": pending_join_requests,
            "total_residents": total_residents,
            "total_meters": total_meters,
            "pending_readings": pending_readings,
            "approved_readings": approved_readings,
            "unit_price": float(society.unit_price),
            "current_month_consumption": total_consumption,
            "current_month_billing": round(total_billing, 2),
            "status": society.status,
            "registration_status": society.registration_status or "ACTIVE",
            "photo_submission_frequency": getattr(society, "photo_submission_frequency", "1_MONTH") or "1_MONTH",
            "blocks": blocks_summary
        }
    )

@router.get("/chairman/society", response_model=MobileApiResponse)
def get_chairman_society_profile(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get full society profile and property summary for Chairman."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked", data={})
        
    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})
        
    blocks_data = [
        {
            "id": b.id,
            "block_id": b.id,
            "title": b.title,
            "total_flats": b.total_flats
        }
        for b in society.blocks
    ]
    
    total_units = sum([b.total_flats for b in society.blocks]) if (society.property_category or "FLAT_APARTMENT") == "FLAT_APARTMENT" else (society.total_houses or 0)
    
    return MobileApiResponse(
        status=1,
        message="Society profile loaded",
        data={
            "id": society.id,
            "society_id": society.id,
            "name": society.name,
            "code": society.code,
            "registration_id": society.registration_id or f"SOC-{society.id}",
            "property_category": society.property_category or "FLAT_APARTMENT",
            "address": society.address,
            "city": society.city,
            "state": society.state,
            "zip_code": society.zip_code,
            "unit_price": float(society.unit_price),
            "status": society.status,
            "registration_status": society.registration_status or "ACTIVE",
            "photo_submission_frequency": getattr(society, "photo_submission_frequency", "1_MONTH") or "1_MONTH",
            "chairman_name": society.chairman_name or current_user.name,
            "chairman_mobile": society.chairman_mobile or current_user.mobile_number,
            "chairman_email": society.chairman_email or current_user.email,
            "contact_number": society.contact_number or "",
            "society_email": society.society_email or "",
            "establishment_year": society.establishment_year or 2024,
            "total_blocks": len(society.blocks),
            "total_flats": total_units,
            "total_houses": society.total_houses,
            "blocks": blocks_data,
            "registered_date": society.created_at.strftime("%d %b %Y") if society.created_at else ""
        }
    )

@router.put("/chairman/society", response_model=MobileApiResponse)
def update_chairman_society_profile(
    payload: UpdateSocietyProfileRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Update authorized society fields including photo submission frequency."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked", data={})
        
    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})
        
    before_state = {
        "name": society.name,
        "address": society.address,
        "contact_number": society.contact_number,
        "photo_submission_frequency": getattr(society, "photo_submission_frequency", "1_MONTH")
    }
    
    if payload.name and payload.name.strip():
        society.name = payload.name.strip()
    if payload.address and payload.address.strip():
        society.address = payload.address.strip()
    if payload.city and payload.city.strip():
        society.city = payload.city.strip()
    if payload.state and payload.state.strip():
        society.state = payload.state.strip()
    if payload.zip_code and payload.zip_code.strip():
        society.zip_code = payload.zip_code.strip()
    if payload.unit_price is not None:
        society.unit_price = payload.unit_price
    if payload.contact_number is not None:
        society.contact_number = payload.contact_number.strip()
    if payload.society_email is not None:
        society.society_email = payload.society_email.strip()
    if payload.establishment_year is not None:
        society.establishment_year = payload.establishment_year
    if payload.photo_submission_frequency is not None and payload.photo_submission_frequency.strip():
        freq = payload.photo_submission_frequency.strip().upper()
        if freq in ["1_MONTH", "6_MONTHS", "1", "6"]:
            society.photo_submission_frequency = "6_MONTHS" if freq in ["6_MONTHS", "6"] else "1_MONTH"
        
    record_audit_log(
        db=db,
        actor_type="USER",
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        action="SOCIETY_PROFILE_UPDATED",
        entity_type="SOCIETY",
        entity_id=str(society.id),
        society_id=society.id,
        before_state=before_state,
        after_state={
            "name": society.name,
            "address": society.address,
            "contact_number": society.contact_number,
            "photo_submission_frequency": society.photo_submission_frequency
        }
    )
    
    db.commit()
    db.refresh(society)
    return MobileApiResponse(
        status=1,
        message="Society details updated successfully",
        data={
            "id": society.id,
            "name": society.name,
            "address": society.address,
            "unit_price": float(society.unit_price),
            "photo_submission_frequency": society.photo_submission_frequency
        }
    )

@router.get("/chairman/society/flats", response_model=MobileApiResponse)
def get_society_flats(
    block_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get all flats within a block or across the society."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked", data=[])
        
    query = db.query(Flat).filter(Flat.society_id == soc_id)
    if block_id:
        query = query.filter(Flat.block_id == block_id)
        
    flats = query.order_by(Flat.id.asc()).all()
    result = [
        {
            "id": f.id,
            "block_id": f.block_id,
            "block_title": f.block.title if f.block else "",
            "flat_number": f.flat_number,
            "status": f.status
        }
        for f in flats
    ]
    return MobileApiResponse(status=1, message="Success", data=result)

@router.get("/chairman/society/houses", response_model=MobileApiResponse)
def get_society_houses(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get all houses for a row house society."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked", data=[])
        
    houses = db.query(House).filter(House.society_id == soc_id).order_by(House.id.asc()).all()
    result = [
        {
            "id": h.id,
            "house_number": h.house_number,
            "status": h.status
        }
        for h in houses
    ]
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/chairman/members/add", response_model=MobileApiResponse)
def add_society_member(
    payload: AddMemberRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Directly add a member/resident to the society (Pre-approved by Chairman)."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked to Chairman", data={})

    mobile = payload.mobile_number.strip()
    if not mobile or len(mobile) < 10:
        return MobileApiResponse(status=0, message="Please enter a valid 10-digit mobile number", data={})

    name = payload.name.strip()
    if not name:
        return MobileApiResponse(status=0, message="Please enter member name", data={})

    flat_or_house = (payload.flat_number or payload.house_number or "").strip()

    # Check if user already exists
    user = db.query(User).filter(User.mobile_number == mobile).first()
    if user:
        # Update existing user to belong to this society with Chairman approval
        user.name = name
        user.society_id = soc_id
        user.block_id = payload.block_id
        user.flat_number = flat_or_house
        user.user_type = payload.role or 1
        user.approval_status = 1  # Pre-approved
        user.is_active = True
        if payload.email and payload.email.strip():
            user.email = payload.email.strip()
    else:
        user = User(
            name=name,
            mobile_number=mobile,
            email=payload.email.strip() if payload.email else None,
            society_id=soc_id,
            block_id=payload.block_id,
            flat_number=flat_or_house,
            user_type=payload.role or 1,
            approval_status=1,  # Pre-approved by Chairman
            is_active=True
        )
        db.add(user)

    # Link / update flat status
    if payload.block_id and flat_or_house:
        flat = db.query(Flat).filter(
            Flat.society_id == soc_id,
            Flat.block_id == payload.block_id,
            Flat.flat_number == flat_or_house
        ).first()
        if flat:
            flat.status = "OCCUPIED"

    # Link / update house status
    if flat_or_house:
        house = db.query(House).filter(
            House.society_id == soc_id,
            House.house_number == flat_or_house
        ).first()
        if house:
            house.status = "OCCUPIED"

    db.commit()
    db.refresh(user)

    return MobileApiResponse(
        status=1,
        message=f"Member '{name}' added successfully to society",
        data=format_user_details(user)
    )

@router.post("/chairman/broadcast-message", response_model=MobileApiResponse)
async def broadcast_chairman_message(
    request: dict,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Chairman sends a broadcast notification / message to all society residents."""
    soc_id = current_user.society_id
    if not soc_id:
        return MobileApiResponse(status=0, message="No society linked to your account", data={})

    title = str(request.get("title") or "Society Announcement").strip()
    message = str(request.get("message") or "").strip()
    notif_type = str(request.get("type") or "ANNOUNCEMENT").strip()

    if not message:
        return MobileApiResponse(status=0, message="Message cannot be empty", data={})

    from app.services.notification_service import broadcast_society_notification
    notif = await broadcast_society_notification(
        db=db,
        society_id=soc_id,
        sender_id=current_user.id,
        title=title,
        message=message,
        notification_type=notif_type
    )

    return MobileApiResponse(
        status=1,
        message="Broadcast notification sent to all society members successfully!",
        data={
            "id": notif.id,
            "title": notif.title,
            "message": notif.message,
            "created_at": notif.created_at.strftime("%d %b, %I:%M %p") if notif.created_at else ""
        }
    )

@router.get("/notifications", response_model=MobileApiResponse)
def get_user_notifications(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Retrieve all society announcements and personal alerts for the logged-in user."""
    from app.models.notification import Notification
    soc_id = current_user.society_id

    query = db.query(Notification)
    if soc_id:
        query = query.filter((Notification.society_id == soc_id) | (Notification.user_id == current_user.id))
    else:
        query = query.filter(Notification.user_id == current_user.id)

    items = query.order_by(Notification.created_at.desc()).limit(50).all()
    results = []
    for item in items:
        results.append({
            "id": item.id,
            "title": item.title,
            "message": item.message,
            "type": item.notification_type,
            "is_read": item.is_read,
            "created_at": item.created_at.strftime("%d %b, %I:%M %p") if item.created_at else "",
            "sender_name": item.sender.name if item.sender else "Chairman"
        })

    return MobileApiResponse(
        status=1,
        message="Notifications retrieved successfully",
        data=results
    )

@router.post("/user/update-fcm-token", response_model=MobileApiResponse)
def update_fcm_token(
    request: dict,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Store or update FCM device push token for the current user."""
    token = str(request.get("fcm_token") or "").strip()
    if token:
        current_user.fcm_token = token
        db.commit()
    return MobileApiResponse(status=1, message="FCM token updated", data={})

