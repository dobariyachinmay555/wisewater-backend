from typing import Optional, List
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.company import CompanyStaff

def get_current_staff(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> CompanyStaff:
    """Authenticate company staff from Bearer JWT token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required"
        )
        
    token = authorization.replace("Bearer ", "").strip()
    payload = decode_access_token(token)
    
    if not payload or payload.get("role") not in ["company_staff", "OWNER", "SUPER_ADMIN", "ADMIN", "SUPPORT", "FINANCE", "READ_ONLY"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin session"
        )
        
    staff_id = payload.get("sub")
    staff = db.query(CompanyStaff).filter(CompanyStaff.id == staff_id, CompanyStaff.is_active == True).first()
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account disabled or not found"
        )
    return staff

def require_roles(allowed_roles: List[str]):
    """Role-based authorization dependency for CMP endpoints."""
    def role_checker(staff: CompanyStaff = Depends(get_current_staff)):
        if staff.role in ["OWNER", "SUPER_ADMIN"]:
            return staff
        if staff.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action"
            )
        return staff
    return role_checker
