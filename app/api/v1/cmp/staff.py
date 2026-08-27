from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.company import CompanyStaff
from app.schemas.cmp import CreateStaffRequest
from app.api.v1.cmp.deps import get_current_staff, require_roles
from app.services.audit_service import record_audit_log

router = APIRouter()

@router.get("")
def list_staff_members(
    current_staff = Depends(require_roles(["OWNER", "SUPER_ADMIN"])),
    db: Session = Depends(get_db)
):
    """List all Company Staff members."""
    staff_list = db.query(CompanyStaff).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "role": s.role,
            "is_active": s.is_active,
            "last_login_at": s.last_login_at.strftime("%Y-%m-%d %H:%M") if s.last_login_at else "Never",
            "created_at": s.created_at.strftime("%Y-%m-%d") if s.created_at else ""
        }
        for s in staff_list
    ]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_staff_member(
    payload: CreateStaffRequest,
    current_staff = Depends(require_roles(["OWNER"])),
    db: Session = Depends(get_db)
):
    """Create a new staff member account (Owner only)."""
    email = payload.email.lower().strip()
    if db.query(CompanyStaff).filter(CompanyStaff.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    staff = CompanyStaff(
        name=payload.name.strip(),
        email=email,
        password_hash=get_password_hash(payload.password),
        role=payload.role.upper(),
        is_active=True
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    
    record_audit_log(
        db=db,
        actor_type="STAFF",
        actor_id=current_staff.id,
        actor_email=current_staff.email,
        action="STAFF_CREATED",
        entity_type="STAFF",
        entity_id=staff.id,
        after_state={"name": staff.name, "email": staff.email, "role": staff.role}
    )
    return {"message": "Staff member created successfully", "id": staff.id}
