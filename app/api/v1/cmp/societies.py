from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.society import Society, Block, Flat, House
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.schemas.cmp import CreateSocietyRequest, UpdateSocietyRequest, AdminTransferChairmanRequest
from app.api.v1.cmp.deps import get_current_staff, require_roles
from app.services.audit_service import record_audit_log
from app.services.sms_service import normalize_indian_mobile

router = APIRouter()

@router.get("")
def list_societies(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """List all registered societies with search, filtering, and live statistics."""
    query = db.query(Society)
    
    if status and status.upper() != "ALL":
        query = query.filter(Society.status == status.upper())
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (Society.name.ilike(term)) |
            (Society.code.ilike(term)) |
            (Society.city.ilike(term)) |
            (Society.chairman_name.ilike(term)) |
            (Society.chairman_mobile.ilike(term))
        )
        
    total = query.count()
    societies = query.order_by(Society.id.desc()).offset((page - 1) * limit).limit(limit).all()
    
    data = []
    for s in societies:
        total_blocks = len(s.blocks)
        total_flats = sum([b.total_flats for b in s.blocks])
        active_residents = db.query(User).filter(User.society_id == s.id, User.is_active == True, User.user_type == 1).count()
        total_meters = db.query(Meter).filter(Meter.society_id == s.id).count()
        
        data.append({
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "address": s.address,
            "city": s.city,
            "state": s.state,
            "zip_code": s.zip_code,
            "unit_price": float(s.unit_price),
            "status": s.status,
            "subscription_status": s.subscription_status,
            "chairman_name": s.chairman_name or "Not Assigned",
            "chairman_mobile": s.chairman_mobile or "N/A",
            "chairman_email": s.chairman_email or "N/A",
            "total_blocks": total_blocks,
            "total_flats": total_flats,
            "active_residents": active_residents,
            "active_meters": total_meters if total_meters > 0 else total_flats,
            "created_at": s.created_at.strftime("%Y-%m-%d") if s.created_at else ""
        })
        
    return {
        "items": data,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.post("", status_code=status.HTTP_201_CREATED)
def create_society(
    payload: CreateSocietyRequest,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Onboard a new Society onto the WiseWater platform."""
    count = db.query(Society).count() + 1
    code = f"SOC-{1000 + count}"
    
    society = Society(
        name=payload.name.strip(),
        code=code,
        address=payload.address.strip(),
        city=payload.city.strip(),
        state=payload.state.strip(),
        zip_code=payload.zip_code.strip(),
        unit_price=payload.unit_price,
        status="ACTIVE",
        subscription_status="ACTIVE",
        subscription_plan_id=payload.subscription_plan_id,
        subscription_start_date=datetime.now(timezone.utc),
        subscription_renewal_date=datetime.now(timezone.utc) + timedelta(days=365),
        chairman_name=payload.chairman_name.strip(),
        chairman_mobile=payload.chairman_mobile.strip(),
        chairman_email=payload.chairman_email
    )
    db.add(society)
    db.flush()
    
    blocks = []
    for i in range(1, payload.number_of_blocks + 1):
        block_title = f"Block {chr(64 + i)}"
        block = Block(
            society_id=society.id,
            title=block_title,
            total_flats=payload.flats_per_block
        )
        blocks.append(block)
    db.add_all(blocks)
    db.flush()
    
    chairman_user = db.query(User).filter(User.mobile_number == payload.chairman_mobile.strip()).first()
    if not chairman_user:
        chairman_user = User(
            name=payload.chairman_name.strip(),
            mobile_number=payload.chairman_mobile.strip(),
            email=payload.chairman_email,
            user_type=3,
            society_id=society.id,
            block_id=blocks[0].id if blocks else None,
            flat_number="101",
            approval_status=1,
            previous_unit=0,
            is_active=True
        )
        db.add(chairman_user)
    else:
        chairman_user.society_id = society.id
        chairman_user.user_type = 3
        chairman_user.name = payload.chairman_name.strip()
        
    db.commit()
    db.refresh(society)
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="SOCIETY_CREATED",
        entity_type="SOCIETY",
        entity_id=str(society.id),
        society_id=society.id,
        after_state={"name": society.name, "code": society.code}
    )
    
    return {
        "id": society.id,
        "name": society.name,
        "code": society.code,
        "message": "Society registered successfully"
    }

@router.get("/{id}")
def get_society_details(
    id: int,
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """Full detail of a society including all member, block, and house records."""
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society not found")
        
    blocks = [{"id": b.id, "title": b.title, "total_flats": b.total_flats} for b in s.blocks]
    houses = [{"id": h.id, "house_number": h.house_number, "status": h.status} for h in s.houses]
    users = db.query(User).filter(User.society_id == s.id).order_by(User.user_type.desc(), User.id.asc()).all()
    
    # Chairman resolution
    chair_name = s.chairman_name
    chair_mobile = s.chairman_mobile
    chair_email = s.chairman_email
    chairman_user = next((u for u in users if u.user_type == 3), None)
    if chairman_user:
        chair_name = chair_name or chairman_user.name
        chair_mobile = chair_mobile or chairman_user.mobile_number
        chair_email = chair_email or chairman_user.email

    residents_data = [
        {
            "id": u.id,
            "name": u.name,
            "mobile": u.mobile_number,
            "email": u.email or "N/A",
            "flat": u.flat_number or "N/A",
            "block": u.block.title if u.block else ("Row House" if s.property_category == "ROW_HOUSE" else "N/A"),
            "role": u.user_type,
            "role_name": "Chairman" if u.user_type == 3 else "Resident",
            "approval_status": u.approval_status,
            "approval_label": "Approved" if u.approval_status == 1 else ("Pending" if u.approval_status == 0 else "Rejected"),
            "previous_unit": u.previous_unit or 0,
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else ""
        }
        for u in users
    ]
    
    prop_cat = s.property_category or ("ROW_HOUSE" if not blocks and houses else "FLAT_APARTMENT")
    total_units = sum([b["total_flats"] for b in blocks]) if prop_cat == "FLAT_APARTMENT" else (s.total_houses or len(houses))

    return {
        "id": s.id,
        "name": s.name,
        "code": s.code,
        "registration_id": s.registration_id or s.code,
        "property_category": prop_cat,
        "address": s.address,
        "city": s.city,
        "state": s.state,
        "zip_code": s.zip_code,
        "unit_price": float(s.unit_price) if s.unit_price else 25.0,
        "status": s.status,
        "registration_status": s.registration_status or "ACTIVE",
        "subscription_status": s.subscription_status or "ACTIVE",
        "chairman_name": chair_name or "Not Assigned",
        "chairman_mobile": chair_mobile or "N/A",
        "chairman_email": chair_email or "N/A",
        "total_blocks": len(blocks),
        "total_flats": total_units,
        "total_houses": s.total_houses or len(houses),
        "total_members": len(residents_data),
        "blocks": blocks,
        "houses": houses,
        "residents": residents_data
    }

@router.patch("/{id}/status")
def toggle_society_status(
    id: int,
    status: str = Query(..., pattern="^(ACTIVE|SUSPENDED|ARCHIVED)$"),
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Suspend, Activate, or Archive a society."""
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society not found")
        
    old_status = s.status
    s.status = status
    if status == "ACTIVE":
        s.registration_status = "ACTIVE"
        chairman = db.query(User).filter(User.society_id == s.id, User.user_type == 3).first()
        if chairman:
            chairman.approval_status = 1
            chairman.is_active = True
    elif status == "SUSPENDED":
        s.registration_status = "SUSPENDED"

    db.commit()
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="SOCIETY_STATUS_CHANGED",
        entity_type="SOCIETY",
        entity_id=str(s.id),
        society_id=s.id,
        before_state={"status": old_status},
        after_state={"status": s.status}
    )
    return {"message": f"Society status updated to {status}"}

@router.delete("/{id}")
def delete_society(
    id: int,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Permanently delete a society and all its associated data."""
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society not found")

    society_name = s.name
    society_code = s.code

    # Clean up related records
    try:
        # Delete bills, readings, meters, flats, houses, users, blocks
        db.query(Bill).filter(Bill.society_id == id).delete(synchronize_session=False)
        db.query(MeterReading).filter(MeterReading.society_id == id).delete(synchronize_session=False)
        db.query(Meter).filter(Meter.society_id == id).delete(synchronize_session=False)
        db.query(Flat).filter(Flat.society_id == id).delete(synchronize_session=False)
        db.query(House).filter(House.society_id == id).delete(synchronize_session=False)
        db.query(User).filter(User.society_id == id).delete(synchronize_session=False)
        db.query(Block).filter(Block.society_id == id).delete(synchronize_session=False)
        db.delete(s)
        db.commit()

        record_audit_log(
            db=db,
            actor_type="STAFF",
            actor_id=current_staff.id,
            actor_email=current_staff.email,
            action="SOCIETY_DELETED",
            entity_type="SOCIETY",
            entity_id=str(id),
            before_state={"name": society_name, "code": society_code}
        )

        return {"status": 1, "message": f"Society '{society_name}' deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete society: {str(e)}")

# --- CMP SOCIETY REGISTRATION APPROVAL & REVIEW WORKFLOW ---

@router.get("/registrations/all")
def list_society_registrations(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """List pending and reviewed society registrations for CMP."""
    query = db.query(Society)
    
    if status and status.upper() != "ALL":
        query = query.filter(Society.registration_status == status.upper())
    else:
        # Default show pending/under-review first or all
        pass
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (Society.name.ilike(term)) |
            (Society.registration_id.ilike(term)) |
            (Society.city.ilike(term)) |
            (Society.chairman_name.ilike(term)) |
            (Society.chairman_mobile.ilike(term))
        )
        
    total = query.count()
    societies = query.order_by(Society.id.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for s in societies:
        prop_category = s.property_category or "FLAT_APARTMENT"
        total_blocks = len(s.blocks)
        total_units = sum([b.total_flats for b in s.blocks]) if prop_category == "FLAT_APARTMENT" else (s.total_houses or 0)
        
        items.append({
            "id": s.id,
            "registration_id": s.registration_id or f"SOC-{s.id}",
            "society_name": s.name,
            "property_category": prop_category,
            "address": s.address,
            "city": s.city,
            "state": s.state,
            "pin_code": s.zip_code,
            "chairman_name": s.chairman_name or "N/A",
            "chairman_mobile": s.chairman_mobile or "N/A",
            "chairman_email": s.chairman_email or "N/A",
            "total_blocks": total_blocks,
            "total_flats_or_houses": total_units,
            "registration_status": s.registration_status or "ACTIVE",
            "status": s.status,
            "rejection_reason": s.rejection_reason,
            "change_request_notes": s.change_request_notes,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else ""
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/registrations/{id}")
def get_society_registration_detail(
    id: int,
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """Inspect full detail of a society registration."""
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society registration not found")
        
    prop_category = s.property_category or "FLAT_APARTMENT"
    blocks_data = [
        {"id": b.id, "title": b.title, "total_flats": b.total_flats}
        for b in s.blocks
    ]
    total_units = sum([b["total_flats"] for b in blocks_data]) if prop_category == "FLAT_APARTMENT" else (s.total_houses or 0)
    
    chairman = db.query(User).filter(User.society_id == s.id, User.user_type == 3).first()
    
    return {
        "id": s.id,
        "registration_id": s.registration_id or f"SOC-{s.id}",
        "code": s.code,
        "society_name": s.name,
        "property_category": prop_category,
        "address": s.address,
        "city": s.city,
        "state": s.state,
        "pin_code": s.zip_code,
        "contact_number": s.contact_number,
        "society_email": s.society_email,
        "establishment_year": s.establishment_year,
        "unit_price": float(s.unit_price),
        "status": s.status,
        "registration_status": s.registration_status or "ACTIVE",
        "rejection_reason": s.rejection_reason,
        "change_request_notes": s.change_request_notes,
        "chairman_name": s.chairman_name or (chairman.name if chairman else "N/A"),
        "chairman_mobile": s.chairman_mobile or (chairman.mobile_number if chairman else "N/A"),
        "chairman_email": s.chairman_email or (chairman.email if chairman else "N/A"),
        "total_blocks": len(blocks_data),
        "total_flats": total_units,
        "total_houses": s.total_houses,
        "blocks": blocks_data,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else ""
    }

@router.post("/registrations/{id}/approve")
def approve_society_registration(
    id: int,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Approve society registration, activate Chairman, and generate official SOC-ID."""
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society registration not found")
        
    s.status = "ACTIVE"
    s.registration_status = "ACTIVE"
    s.subscription_status = "ACTIVE"
    
    # Generate official code: SOC-XXXX (collision-free)
    if not s.code or s.code.startswith("TMP-"):
        existing_codes = db.query(Society.code).filter(Society.code.like("SOC-%")).all()
        max_num = 1000
        for (c,) in existing_codes:
            if c:
                try:
                    num = int(c.replace("SOC-", "").strip())
                    if num > max_num:
                        max_num = num
                except Exception:
                    pass
        s.code = f"SOC-{max_num + 1}"
        
    # Activate Chairman user
    chairman = db.query(User).filter(User.society_id == s.id, User.user_type == 3).first()
    if chairman:
        chairman.approval_status = 1  # Approved
        chairman.is_active = True
        
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="SOCIETY_REGISTRATION_APPROVED",
        entity_type="SOCIETY",
        entity_id=str(s.id),
        society_id=s.id,
        after_state={"status": "ACTIVE", "code": s.code}
    )
    
    db.commit()
    return {
        "status": 1,
        "message": f"Society {s.name} approved successfully with code {s.code}",
        "code": s.code
    }

@router.post("/registrations/{id}/reject")
def reject_society_registration(
    id: int,
    payload: dict,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Reject society registration with mandatory reason."""
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")
        
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society registration not found")
        
    s.status = "REJECTED"
    s.registration_status = "REJECTED"
    s.rejection_reason = reason
    
    chairman = db.query(User).filter(User.society_id == s.id, User.user_type == 3).first()
    if chairman:
        chairman.approval_status = 2  # Rejected
        
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="SOCIETY_REGISTRATION_REJECTED",
        entity_type="SOCIETY",
        entity_id=str(s.id),
        society_id=s.id,
        after_state={"status": "REJECTED", "reason": reason}
    )
    
    db.commit()
    return {"status": 1, "message": "Society registration rejected", "reason": reason}

@router.post("/registrations/{id}/request-changes")
def request_changes_society_registration(
    id: int,
    payload: dict,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Request changes on a society registration."""
    notes = str(payload.get("notes") or "").strip()
    if not notes:
        raise HTTPException(status_code=400, detail="Change request notes are required")
        
    s = db.query(Society).filter(Society.id == id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Society registration not found")
        
    s.registration_status = "CHANGES_REQUIRED"
    s.change_request_notes = notes
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="SOCIETY_REGISTRATION_CHANGES_REQUESTED",
        entity_type="SOCIETY",
        entity_id=str(s.id),
        society_id=s.id,
        after_state={"registration_status": "CHANGES_REQUIRED", "notes": notes}
    )
    
    db.commit()
    return {"status": 1, "message": "Changes requested successfully", "notes": notes}

@router.post("/{id}/transfer-chairman")
async def admin_transfer_chairman(
    id: int,
    payload: AdminTransferChairmanRequest,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """CMP Administrative Emergency Override: Transfer society Chairman.
    
    Used when the Chairman lost access, left without notice, or by society committee resolution.
    Mandates an administrative reason recorded in immutable audit log.
    """
    society = db.query(Society).filter(Society.id == id).first()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")

    new_mobile = normalize_indian_mobile(payload.new_mobile_number)
    if not new_mobile:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit Indian mobile number")

    new_name = payload.new_name.strip()
    if len(new_name) < 2:
        raise HTTPException(status_code=400, detail="New Chairman name must be at least 2 characters")

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Administrative reason is required for Chairman transfer")

    # Find existing chairman for this society
    old_chairman = db.query(User).filter(User.society_id == society.id, User.user_type == 3).first()

    # Check candidate
    candidate_user = db.query(User).filter(User.mobile_number == new_mobile).first()
    if candidate_user:
        if candidate_user.user_type == 3 and candidate_user.society_id != society.id:
            raise HTTPException(status_code=400, detail="Candidate is already Chairman of another society")
        if candidate_user.society_id and candidate_user.society_id != society.id:
            raise HTTPException(status_code=400, detail="Candidate belongs to another society")
        candidate_user.name = new_name
        if payload.new_email:
            candidate_user.email = payload.new_email
        candidate_user.user_type = 3
        candidate_user.society_id = society.id
        candidate_user.approval_status = 1
        candidate_user.is_active = True
    else:
        candidate_user = User(
            name=new_name,
            mobile_number=new_mobile,
            email=payload.new_email,
            user_type=3,
            society_id=society.id,
            approval_status=1,
            previous_unit=0,
            is_active=True
        )
        db.add(candidate_user)
        db.flush()

    demote = payload.demote_old_to_resident if payload.demote_old_to_resident is not None else True
    before_state = {
        "society_id": society.id,
        "society_name": society.name,
        "old_chairman_id": old_chairman.id if old_chairman else None,
        "old_chairman_name": old_chairman.name if old_chairman else society.chairman_name,
        "old_chairman_mobile": old_chairman.mobile_number if old_chairman else society.chairman_mobile,
    }

    if old_chairman:
        if demote:
            old_chairman.user_type = 1
        else:
            old_chairman.user_type = 1
            old_chairman.is_active = False

    society.chairman_name = new_name
    society.chairman_mobile = new_mobile
    if payload.new_email:
        society.chairman_email = payload.new_email

    now_utc = datetime.now(timezone.utc)
    after_state = {
        "new_chairman_id": candidate_user.id,
        "new_chairman_name": new_name,
        "new_chairman_mobile": new_mobile,
        "reason": reason,
        "transferred_by_staff_id": current_staff.id,
        "transferred_by_staff_email": current_staff.email,
        "transferred_at": now_utc.isoformat()
    }

    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="ADMIN_CHAIRMAN_TRANSFERRED",
        entity_type="SOCIETY",
        entity_id=str(society.id),
        society_id=society.id,
        before_state=before_state,
        after_state=after_state
    )

    db.commit()
    db.refresh(society)
    db.refresh(candidate_user)

    # Send broadcast notice to society members regarding new Chairman
    try:
        from app.services.notification_service import broadcast_society_notification
        await broadcast_society_notification(
            db=db,
            society_id=society.id,
            sender_id=candidate_user.id,
            title="Chairman Changed",
            message=f"The Chairman of {society.name} has been changed to {new_name}.",
            notification_type="ANNOUNCEMENT",
            data={
                "type": "CHAIRMAN_CHANGED",
                "society_id": str(society.id),
                "new_chairman_name": new_name,
                "new_chairman_id": str(candidate_user.id)
            }
        )
    except Exception as notif_err:
        print(f"[CMP TRANSFER NOTIF NOTE] Broadcast notice skipped: {notif_err}")

    return {
        "status": 1,
        "message": f"Chairman transferred to {new_name} ({new_mobile}) successfully",
        "data": {
            "society_id": society.id,
            "new_chairman_name": new_name,
            "new_chairman_mobile": new_mobile
        }
    }

