from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.models.society import Society
from app.api.v1.cmp.deps import get_current_staff, require_roles
from app.services.audit_service import record_audit_log

router = APIRouter()

@router.get("")
def list_users(
    search: Optional[str] = Query(None),
    society_id: Optional[int] = Query(None),
    user_type: Optional[int] = Query(None),
    unassigned_only: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """List all platform users with filtering by society, role, and search term."""
    query = db.query(User)
    
    if society_id:
        query = query.filter(User.society_id == society_id)
    if user_type:
        query = query.filter(User.user_type == user_type)
    if unassigned_only is True:
        query = query.filter(User.society_id.is_(None))
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (User.name.ilike(term)) |
            (User.mobile_number.ilike(term)) |
            (User.email.ilike(term)) |
            (User.flat_number.ilike(term))
        )
        
    total = query.count()
    users = query.order_by(User.id.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for u in users:
        is_unassigned = u.society_id is None
        items.append({
            "id": u.id,
            "name": u.name,
            "mobile_number": u.mobile_number,
            "email": u.email or "N/A",
            "user_type": u.user_type,
            "role_name": "Chairman" if u.user_type == 3 else ("Committee Admin" if u.user_type == 2 else "Resident"),
            "society_id": u.society_id,
            "society_name": u.society.name if u.society else "Unassigned",
            "block_title": u.block.title if u.block else "N/A",
            "flat_number": u.flat_number or "N/A",
            "is_unassigned": is_unassigned,
            "approval_status": u.approval_status,
            "previous_unit": u.previous_unit,
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else ""
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.patch("/{id}/status")
def toggle_user_status(
    id: int,
    is_active: bool = Query(...),
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Activate or suspend user account."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_active = is_active
    db.commit()
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="USER_STATUS_TOGGLED",
        entity_type="USER",
        entity_id=str(user.id),
        society_id=user.society_id,
        after_state={"is_active": is_active}
    )
    return {"message": f"User {'activated' if is_active else 'suspended'} successfully"}
