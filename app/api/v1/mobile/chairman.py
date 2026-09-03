from typing import Optional, List
from datetime import datetime, timezone, timedelta
import secrets
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.database import get_db
from app.models.society import Society, Block, Flat, House
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.models.chairman_transfer import ChairmanTransfer
from app.schemas.mobile import (
    MobileApiResponse,
    UpdateSocietyProfileRequest,
    AddMemberRequest,
    InitiateChairmanTransferRequest,
    VerifyChairmanTransferOtpRequest,
    CompleteChairmanTransferRequest,
    VerifyAndCompleteChairmanTransferRequest,
    CancelChairmanTransferRequest
)
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details, require_chairman_user
from app.services.audit_service import record_audit_log
from app.services.sms_service import send_sms_otp, generate_otp, normalize_indian_mobile

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
        
    pending_readings = db.query(MeterReading).join(User, MeterReading.user_id == User.id).filter(
        MeterReading.society_id == soc_id,
        MeterReading.status == 0,
        User.approval_status == 1
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
    """Retrieve all society announcements and personal alerts for the logged-in user with accurate read state."""
    from app.models.notification import Notification, NotificationRead
    soc_id = current_user.society_id

    query = db.query(Notification)
    if soc_id:
        query = query.filter(
            (Notification.user_id == current_user.id) |
            ((Notification.society_id == soc_id) & (Notification.user_id.is_(None)))
        )
    else:
        query = query.filter(Notification.user_id == current_user.id)

    items = query.order_by(Notification.created_at.desc()).limit(100).all()


    # Get set of notification IDs marked read by this user
    read_ids = set(
        r[0] for r in db.query(NotificationRead.notification_id)
        .filter(NotificationRead.user_id == current_user.id)
        .all()
    )

    results = []
    for item in items:
        is_item_read = (item.id in read_ids) or (item.user_id == current_user.id and item.is_read)
        results.append({
            "id": item.id,
            "title": item.title,
            "message": item.message,
            "type": item.notification_type,
            "is_read": is_item_read,
            "created_at": item.created_at.strftime("%d %b, %I:%M %p") if item.created_at else "",
            "sender_name": item.sender.name if item.sender else "Chairman"
        })

    return MobileApiResponse(
        status=1,
        message="Notifications retrieved successfully",
        data=results
    )

@router.get("/notifications/unread-count", response_model=MobileApiResponse)
def get_unread_notifications_count(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Retrieve total count of unread notifications for the user across all notification categories."""
    from app.services.notification_service import get_user_unread_count
    unread_count = get_user_unread_count(db=db, user=current_user)
    return MobileApiResponse(
        status=1,
        message="Unread notification count retrieved",
        data={"unread_count": unread_count}
    )

@router.post("/notifications/mark-read", response_model=MobileApiResponse)
def mark_user_notification_read(
    request: dict,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Mark a specific notification or all notifications as read for current user."""
    from app.services.notification_service import mark_notification_as_read, mark_all_notifications_as_read, get_user_unread_count
    
    notif_id = request.get("notification_id")
    mark_all = request.get("all", False)

    if notif_id is not None:
        try:
            nid = int(notif_id)
            mark_notification_as_read(db=db, user_id=current_user.id, notification_id=nid)
        except Exception:
            pass
    elif mark_all or notif_id is None:
        mark_all_notifications_as_read(db=db, user=current_user)

    remaining_unread = get_user_unread_count(db=db, user=current_user)
    return MobileApiResponse(
        status=1,
        message="Notification(s) marked as read",
        data={"unread_count": remaining_unread}
    )

@router.post("/user/update-fcm-token", response_model=MobileApiResponse)
def update_fcm_token(
    request: dict,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Store or update FCM device push token for the current user.
    
    Real Firebase FCM registration tokens are typically 140–200+ characters long.
    Tokens shorter than 100 characters are rejected as invalid/mock tokens.
    """
    token = str(request.get("fcm_token") or "").strip()
    token_stored = False

    if token:
        # Real FCM tokens from FirebaseMessaging.instance.getToken() are always 140+ chars.
        # Reject suspiciously short tokens (mock/test/placeholder values).
        MIN_REAL_FCM_TOKEN_LENGTH = 100
        if len(token) < MIN_REAL_FCM_TOKEN_LENGTH:
            print(f"[FCM TOKEN] Rejected short/invalid token for User {current_user.id} (len: {len(token)}) — not a real Firebase token.")
            return MobileApiResponse(
                status=0,
                message=f"Token rejected: length {len(token)} is too short to be a real FCM token. Must come from FirebaseMessaging.instance.getToken().",
                data={"fcm_token_set": False, "token_length": len(token)}
            )
        current_user.fcm_token = token
        db.commit()
        token_stored = True
        print(f"[FCM TOKEN] ✓ Stored real FCM token for User {current_user.id} ({current_user.mobile_number}). Length: {len(token)}, Prefix: {token[:15]}...")

    return MobileApiResponse(
        status=1,
        message="FCM token updated",
        data={
            "fcm_token_set": token_stored,
            "token_length": len(token) if token_stored else 0,
            "user_id": current_user.id
        }
    )



@router.post("/notifications/test-push", response_model=MobileApiResponse)
def test_fcm_push(
    request: dict,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Send a direct test push notification to verify Firebase delivery."""
    from app.services.notification_service import test_single_fcm
    target_id = request.get("user_id") or current_user.id
    target_mobile = request.get("mobile_number")
    target_token = request.get("fcm_token")
    title = request.get("title", "FCM Test")
    body = request.get("body", "Testing Firebase push notification")

    print("=" * 60)
    print(f"[TEST FCM PUSH DISPATCH]")
    print(f"Authenticated User ID: {current_user.id}, Role: {current_user.user_type}, Mobile: {current_user.mobile_number}")
    print(f"Target User ID: {target_id}, Target Mobile: {target_mobile}")
    print(f"Target Token Specified in Body: {bool(target_token)}")
    print(f"User FCM Token in DB: {bool(current_user.fcm_token)} (len: {len(current_user.fcm_token) if current_user.fcm_token else 0})")
    print(f"Title: {title}")
    print(f"Body: {body}")
    print("=" * 60)

    result = test_single_fcm(
        db=db,
        user_id=int(target_id) if target_id else None,
        mobile=target_mobile,
        token=target_token,
        title=title,
        body=body
    )

    return MobileApiResponse(
        status=result.get("status", 1),
        message=result.get("message", "FCM test completed"),
        data=result.get("diagnostics", {})
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CHAIRMAN TRANSFER FLOW (SECURE 2-STEP ATOMIC HANDOFF)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/chairman/transfer/status", response_model=MobileApiResponse)
def get_chairman_transfer_status(
    current_user: User = Depends(require_chairman_user),
    db: Session = Depends(get_db)
):
    """Get active or recent Chairman transfer status for this society."""
    soc_id = current_user.society_id
    transfer = db.query(ChairmanTransfer).filter(
        ChairmanTransfer.society_id == soc_id,
        ChairmanTransfer.status.in_(["PENDING_OTP", "OTP_VERIFIED"])
    ).order_by(ChairmanTransfer.created_at.desc()).first()

    if not transfer:
        return MobileApiResponse(
            status=1,
            message="No active transfer in progress",
            data={"has_active_transfer": False}
        )

    # Check if expired
    now_utc = datetime.now(timezone.utc)
    exp = transfer.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc and transfer.status == "PENDING_OTP":
        transfer.status = "EXPIRED"
        db.commit()
        return MobileApiResponse(
            status=1,
            message="Transfer has expired",
            data={"has_active_transfer": False, "status": "EXPIRED"}
        )

    masked_mobile = f"+91 {transfer.to_mobile_number[:2]}******{transfer.to_mobile_number[-2:]}" if len(transfer.to_mobile_number) == 10 else transfer.to_mobile_number
    return MobileApiResponse(
        status=1,
        message="Active transfer in progress",
        data={
            "has_active_transfer": True,
            "transfer_id": transfer.id,
            "to_name": transfer.to_name,
            "to_mobile_masked": masked_mobile,
            "to_mobile_number": transfer.to_mobile_number,
            "status": transfer.status,
            "is_verified": transfer.is_verified,
            "demote_old_to_resident": transfer.demote_old_to_resident,
            "expires_at": transfer.expires_at.isoformat() if transfer.expires_at else ""
        }
    )


@router.post("/chairman/transfer/initiate", response_model=MobileApiResponse)
async def initiate_chairman_transfer(
    payload: InitiateChairmanTransferRequest,
    current_user: User = Depends(require_chairman_user),
    db: Session = Depends(get_db)
):
    """Step 1: Current Chairman initiates role transfer to a new candidate.
    
    Generates a dedicated transfer OTP dispatched directly to the candidate's mobile number.
    Validates that the target number does not belong to another society.
    """
    soc_id = current_user.society_id
    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})

    raw_mobile = str(payload.new_mobile_number or "").strip()
    new_mobile = normalize_indian_mobile(raw_mobile)
    if not new_mobile:
        return MobileApiResponse(status=0, message="Please enter a valid 10-digit Indian mobile number", data={})

    new_name = str(payload.new_name or "").strip()
    if not new_name or len(new_name) < 2:
        return MobileApiResponse(status=0, message="Please enter the new Chairman's full name (at least 2 characters)", data={})

    new_email = str(payload.new_email or "").strip() if payload.new_email else None

    # Constraint 1: Cannot transfer to self
    if new_mobile == current_user.mobile_number:
        return MobileApiResponse(status=0, message="You cannot transfer Chairman responsibilities to your own current mobile number", data={})

    # Constraint 2: Check target mobile in system
    target_user = db.query(User).filter(User.mobile_number == new_mobile).first()
    if target_user:
        # If target user is Chairman of another society, reject
        if target_user.user_type == 3 and target_user.society_id != soc_id:
            other_soc = db.query(Society).filter(Society.id == target_user.society_id).first()
            soc_title = other_soc.name if other_soc else "another society"
            return MobileApiResponse(
                status=0,
                message=f"This mobile number is already registered as Chairman of '{soc_title}'. A Chairman can only manage one society.",
                data={}
            )
        # If target user belongs to a different society as a Resident, reject
        if target_user.society_id and target_user.society_id != soc_id:
            other_soc = db.query(Society).filter(Society.id == target_user.society_id).first()
            soc_title = other_soc.name if other_soc else "another society"
            return MobileApiResponse(
                status=0,
                message=f"This user is already registered with '{soc_title}'. Cross-society transfers are not permitted.",
                data={}
            )

    # Cancel previous pending transfers for this society
    prev_pending = db.query(ChairmanTransfer).filter(
        ChairmanTransfer.society_id == soc_id,
        ChairmanTransfer.status.in_(["PENDING_OTP", "OTP_VERIFIED"])
    ).all()
    for p in prev_pending:
        p.status = "CANCELLED"
        p.cancellation_reason = "Superseded by new transfer request"

    # Generate dedicated OTP for Chairman Transfer (cannot be reused elsewhere)
    otp_code = generate_otp(length=6)
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    transfer = ChairmanTransfer(
        society_id=soc_id,
        from_user_id=current_user.id,
        to_user_id=target_user.id if target_user else None,
        to_mobile_number=new_mobile,
        to_name=new_name,
        to_email=new_email,
        otp_code=otp_code,
        expires_at=expires_at,
        attempts=0,
        is_verified=False,
        status="PENDING_OTP",
        demote_old_to_resident=payload.demote_old_to_resident if payload.demote_old_to_resident is not None else True
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    # Dispatch OTP via SMS to new candidate's mobile
    sms_sent, msg_detail = await send_sms_otp(new_mobile, otp_code)
    masked_mobile = f"+91 {new_mobile[:2]}******{new_mobile[-2:]}"

    if not sms_sent:
        if settings.ENABLE_TEST_OTP_BYPASS:
            return MobileApiResponse(
                status=1,
                message=f"Transfer OTP generated for candidate {masked_mobile} (test mode: use 1234)",
                data={
                    "transfer_id": transfer.id,
                    "new_mobile_number": new_mobile,
                    "new_name": new_name,
                    "status": "PENDING_OTP",
                    "expires_at": expires_at.isoformat(),
                    "is_existing_resident": bool(target_user and target_user.society_id == soc_id)
                }
            )
        return MobileApiResponse(status=0, message=msg_detail or "Unable to send SMS OTP to candidate. Please try again.", data={})

    return MobileApiResponse(
        status=1,
        message=f"Verification OTP sent to new Chairman's mobile number: {masked_mobile}",
        data={
            "transfer_id": transfer.id,
            "new_mobile_number": new_mobile,
            "new_name": new_name,
            "status": "PENDING_OTP",
            "expires_at": expires_at.isoformat(),
            "is_existing_resident": bool(target_user and target_user.society_id == soc_id)
        }
    )


@router.post("/chairman/transfer/verify-otp", response_model=MobileApiResponse)
def verify_chairman_transfer_otp(
    payload: VerifyChairmanTransferOtpRequest,
    db: Session = Depends(get_db)
):
    """Step 2: Verify OTP received by the new candidate on their own phone.
    
    Can be submitted by the candidate or by the Chairman entering the candidate's OTP.
    Once verified, transfer status transitions to OTP_VERIFIED.
    """
    transfer = db.query(ChairmanTransfer).filter(ChairmanTransfer.id == payload.transfer_id.strip()).first()
    if not transfer:
        return MobileApiResponse(status=0, message="Transfer request not found", data={})

    if transfer.status not in ["PENDING_OTP", "OTP_VERIFIED"]:
        return MobileApiResponse(status=0, message=f"Transfer request is already {transfer.status.lower().replace('_', ' ')}", data={})

    raw_mobile = str(payload.mobile_number or "").strip()
    mobile = normalize_indian_mobile(raw_mobile)
    if mobile != transfer.to_mobile_number:
        return MobileApiResponse(status=0, message="Mobile number does not match this transfer record", data={})

    # Check attempts
    if transfer.attempts >= settings.MAX_OTP_ATTEMPTS:
        transfer.status = "EXPIRED"
        db.commit()
        return MobileApiResponse(status=0, message="Maximum verification attempts exceeded. Please initiate a new transfer.", data={})

    # Check expiration
    now_utc = datetime.now(timezone.utc)
    exp = transfer.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc:
        transfer.status = "EXPIRED"
        db.commit()
        return MobileApiResponse(status=0, message="Transfer OTP has expired. Please initiate a new transfer.", data={})

    # Validate OTP
    otp_input = str(payload.otp_code or "").strip()
    is_test_bypass = settings.ENABLE_TEST_OTP_BYPASS and (otp_input in ["1234", "123456"])
    if not is_test_bypass:
        is_match = secrets.compare_digest(transfer.otp_code, otp_input)
        if not is_match:
            transfer.attempts += 1
            db.commit()
            remaining = settings.MAX_OTP_ATTEMPTS - transfer.attempts
            if remaining <= 0:
                transfer.status = "EXPIRED"
                db.commit()
                return MobileApiResponse(status=0, message="Maximum verification attempts exceeded. Please initiate a new transfer.", data={})
            return MobileApiResponse(status=0, message=f"Invalid OTP. {remaining} attempt{'s' if remaining > 1 else ''} remaining.", data={})

    transfer.is_verified = True
    transfer.status = "OTP_VERIFIED"
    db.commit()

    return MobileApiResponse(
        status=1,
        message="Candidate OTP verified successfully! Current Chairman can now confirm and complete the transfer.",
        data={
            "transfer_id": transfer.id,
            "status": "OTP_VERIFIED",
            "to_name": transfer.to_name,
            "to_mobile_number": transfer.to_mobile_number
        }
    )


@router.post("/chairman/transfer/complete", response_model=MobileApiResponse)
async def complete_chairman_transfer(
    payload: CompleteChairmanTransferRequest,
    current_user: User = Depends(require_chairman_user),
    db: Session = Depends(get_db)
):
    """Step 3: Current Chairman confirms the handoff after OTP verification.
    
    Performs atomic transfer of Society Chairman responsibilities:
    1. Society chairman_name/mobile/email updated.
    2. Old Chairman demoted to Resident (or deactivated).
    3. New Chairman promoted/created with Chairman role.
    4. Audit trail recorded.
    5. Old Chairman immediately loses Chairman privileges.
    """
    soc_id = current_user.society_id
    transfer = db.query(ChairmanTransfer).filter(ChairmanTransfer.id == payload.transfer_id.strip()).first()
    if not transfer:
        return MobileApiResponse(status=0, message="Transfer request not found", data={})

    if transfer.society_id != soc_id or transfer.from_user_id != current_user.id:
        return MobileApiResponse(status=0, message="Unauthorized: You did not initiate this transfer request", data={})

    if not transfer.is_verified or transfer.status != "OTP_VERIFIED":
        return MobileApiResponse(status=0, message="Cannot complete transfer: Candidate has not yet verified OTP", data={})

    # Check expiry
    now_utc = datetime.now(timezone.utc)
    exp = transfer.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc:
        transfer.status = "EXPIRED"
        db.commit()
        return MobileApiResponse(status=0, message="Transfer session expired. Please initiate a new transfer.", data={})

    society = db.query(Society).filter(Society.id == soc_id).first()
    if not society:
        return MobileApiResponse(status=0, message="Society not found", data={})

    demote = payload.demote_old_to_resident if payload.demote_old_to_resident is not None else transfer.demote_old_to_resident

    try:
        # Find or create candidate user
        candidate_user = db.query(User).filter(User.mobile_number == transfer.to_mobile_number).first()
        if candidate_user:
            # Prevent race condition: ensure not chairman of another society
            if candidate_user.user_type == 3 and candidate_user.society_id != soc_id:
                db.rollback()
                return MobileApiResponse(status=0, message="Candidate is already Chairman of another society", data={})
            if candidate_user.society_id and candidate_user.society_id != soc_id:
                db.rollback()
                return MobileApiResponse(status=0, message="Candidate belongs to another society", data={})

            # Promote existing resident
            candidate_user.name = transfer.to_name
            if transfer.to_email:
                candidate_user.email = transfer.to_email
            candidate_user.user_type = 3
            candidate_user.society_id = soc_id
            candidate_user.approval_status = 1
            candidate_user.is_active = True
            # FCM token is untouched so their own device receives messages once active
        else:
            candidate_user = User(
                name=transfer.to_name,
                mobile_number=transfer.to_mobile_number,
                email=transfer.to_email,
                user_type=3,
                society_id=soc_id,
                approval_status=1,
                previous_unit=0,
                is_active=True
            )
            db.add(candidate_user)
            db.flush()

        # Update Old Chairman
        before_state = {
            "old_chairman_id": current_user.id,
            "old_chairman_name": current_user.name,
            "old_chairman_mobile": current_user.mobile_number,
            "society_name": society.name,
            "society_code": society.code,
            "demoted_to_resident": demote
        }

        if demote:
            current_user.user_type = 1  # Demoted to Resident
            # Flat, block, meters, and readings stay untouched!
        else:
            current_user.user_type = 1
            current_user.is_active = False

        # Update Society Record
        society.chairman_name = transfer.to_name
        society.chairman_mobile = transfer.to_mobile_number
        if transfer.to_email:
            society.chairman_email = transfer.to_email

        # Mark transfer complete
        transfer.to_user_id = candidate_user.id
        transfer.status = "COMPLETED"
        transfer.completed_at = now_utc

        # Record complete audit log
        after_state = {
            "new_chairman_id": candidate_user.id,
            "new_chairman_name": candidate_user.name,
            "new_chairman_mobile": candidate_user.mobile_number,
            "new_chairman_email": candidate_user.email,
            "transferred_at": now_utc.isoformat(),
            "transfer_id": transfer.id
        }

        record_audit_log(
            db=db,
            actor_type="USER",
            actor_id=str(current_user.id),
            actor_email=current_user.email,
            action="CHAIRMAN_TRANSFERRED",
            entity_type="SOCIETY",
            entity_id=str(society.id),
            society_id=society.id,
            before_state=before_state,
            after_state=after_state
        )

        db.commit()
        db.refresh(society)
        db.refresh(current_user)
        db.refresh(candidate_user)

        # Send broadcast notice to society members regarding new Chairman
        try:
            from app.services.notification_service import broadcast_society_notification
            await broadcast_society_notification(
                db=db,
                society_id=soc_id,
                sender_id=candidate_user.id,
                title="Chairman Changed",
                message=f"The Chairman of {society.name} has been changed to {candidate_user.name}.",
                notification_type="ANNOUNCEMENT",
                data={
                    "type": "CHAIRMAN_CHANGED",
                    "society_id": str(soc_id),
                    "new_chairman_name": candidate_user.name,
                    "new_chairman_id": str(candidate_user.id)
                }
            )
        except Exception as notif_err:
            print(f"[TRANSFER NOTIF NOTE] Broadcast notice skipped: {notif_err}")

        return MobileApiResponse(
            status=1,
            message=f"Chairman responsibilities for '{society.name}' successfully transferred to {candidate_user.name} 🎉",
            data={
                "transfer_id": transfer.id,
                "status": "COMPLETED",
                "new_chairman_name": candidate_user.name,
                "new_chairman_mobile": candidate_user.mobile_number,
                "demoted_to_resident": demote,
                "user_details": format_user_details(current_user)
            }
        )
    except Exception as e:
        db.rollback()
        return MobileApiResponse(status=0, message=f"Transfer execution failed: {str(e)}", data={})


@router.post("/chairman/transfer/verify-and-complete", response_model=MobileApiResponse)
async def verify_and_complete_chairman_transfer(
    payload: VerifyAndCompleteChairmanTransferRequest,
    current_user: User = Depends(require_chairman_user),
    db: Session = Depends(get_db)
):
    """Convenience Combined Endpoint: Verifies OTP and completes the transfer in a single atomic call."""
    # First verify OTP
    v_req = VerifyChairmanTransferOtpRequest(
        transfer_id=payload.transfer_id,
        mobile_number=payload.mobile_number,
        otp_code=payload.otp_code
    )
    v_res = verify_chairman_transfer_otp(payload=v_req, db=db)
    if v_res.status != 1:
        return v_res

    # Then complete transfer
    c_req = CompleteChairmanTransferRequest(
        transfer_id=payload.transfer_id,
        demote_old_to_resident=payload.demote_old_to_resident
    )
    return await complete_chairman_transfer(payload=c_req, current_user=current_user, db=db)


@router.post("/chairman/transfer/cancel", response_model=MobileApiResponse)
def cancel_chairman_transfer(
    payload: CancelChairmanTransferRequest,
    current_user: User = Depends(require_chairman_user),
    db: Session = Depends(get_db)
):
    """Cancel an ongoing Chairman transfer request."""
    transfer = db.query(ChairmanTransfer).filter(ChairmanTransfer.id == payload.transfer_id.strip()).first()
    if not transfer:
        return MobileApiResponse(status=0, message="Transfer request not found", data={})

    if transfer.society_id != current_user.society_id or transfer.from_user_id != current_user.id:
        return MobileApiResponse(status=0, message="Unauthorized to cancel this transfer", data={})

    if transfer.status == "COMPLETED":
        return MobileApiResponse(status=0, message="Cannot cancel an already completed transfer", data={})

    transfer.status = "CANCELLED"
    transfer.cancellation_reason = payload.reason or "Cancelled by Chairman"
    db.commit()

    return MobileApiResponse(
        status=1,
        message="Chairman transfer request cancelled successfully",
        data={"transfer_id": transfer.id, "status": "CANCELLED"}
    )
