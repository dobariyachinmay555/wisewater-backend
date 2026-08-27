from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.reading import MeterReading
from app.models.user import User
from app.models.society import Society
from app.schemas.cmp import UpdateReadingStatusCMPRequest
from app.api.v1.cmp.deps import get_current_staff, require_roles
from app.services.audit_service import record_audit_log
from app.services.billing_service import generate_bill_for_reading

router = APIRouter()

@router.get("")
def list_readings(
    society_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    status: Optional[int] = Query(None),  # 0: Pending, 1: Approved, 2: Rejected, 3: Flagged
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """List all meter readings with image proofs and calculation status."""
    query = db.query(MeterReading)
    
    if society_id:
        query = query.filter(MeterReading.society_id == society_id)
    if user_id:
        query = query.filter(MeterReading.user_id == user_id)
    if status is not None:
        query = query.filter(MeterReading.status == status)
        
    total = query.count()
    readings = query.order_by(MeterReading.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for r in readings:
        user = db.query(User).filter(User.id == r.user_id).first()
        society = db.query(Society).filter(Society.id == r.society_id).first()
        
        items.append({
            "id": r.id,
            "society_name": society.name if society else f"Society #{r.society_id}",
            "resident_name": user.name if user else f"User #{r.user_id}",
            "mobile_number": user.mobile_number if user else "",
            "flat_number": user.flat_number if user else "",
            "block_title": r.block.title if r.block else "",
            "previous_unit": r.previous_unit,
            "current_unit": r.current_unit,
            "total_unit": r.total_unit,
            "unit_price": float(r.unit_price),
            "total_price": float(r.total_price),
            "image_url": r.image_url or "",
            "status": r.status,  # 0: Pending, 1: Approved, 2: Rejected, 3: Flagged
            "status_label": "Pending" if r.status == 0 else ("Approved" if r.status == 1 else ("Rejected" if r.status == 2 else "Flagged")),
            "remarks": r.remarks or "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.patch("/{id}/status")
def update_reading_status(
    id: int,
    payload: UpdateReadingStatusCMPRequest,
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Approve, Reject, or Flag a meter reading from CMP."""
    reading = db.query(MeterReading).filter(MeterReading.id == id).first()
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
        
    old_status = reading.status
    reading.status = payload.status
    if payload.remarks:
        reading.remarks = payload.remarks
    reading.approved_at = datetime.now(timezone.utc)
    
    if payload.status == 1:
        # Update user baseline and generate invoice
        user = db.query(User).filter(User.id == reading.user_id).first()
        if user:
            user.previous_unit = reading.current_unit
        generate_bill_for_reading(db, reading)
        
    db.commit()
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="READING_STATUS_MODIFIED",
        entity_type="READING",
        entity_id=str(reading.id),
        society_id=reading.society_id,
        before_state={"status": old_status},
        after_state={"status": reading.status, "remarks": payload.remarks}
    )
    return {"message": "Reading status updated successfully"}
