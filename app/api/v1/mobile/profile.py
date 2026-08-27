from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.mobile import MobileApiResponse
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details

router = APIRouter()

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

@router.get("/profile", response_model=MobileApiResponse)
def get_profile(
    current_user: User = Depends(get_current_mobile_user)
):
    """Return authenticated mobile user profile."""
    return MobileApiResponse(
        status=1,
        message="Profile loaded",
        data=format_user_details(current_user)
    )

@router.post("/profile/update", response_model=MobileApiResponse)
@router.put("/profile", response_model=MobileApiResponse)
def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Update user's personal details (Name & Email)."""
    if payload.name and payload.name.strip():
        current_user.name = payload.name.strip()
    if payload.email is not None:
        current_user.email = payload.email.strip()
        
    db.commit()
    db.refresh(current_user)
    return MobileApiResponse(
        status=1,
        message="Profile updated successfully",
        data=format_user_details(current_user)
    )

@router.post("/logout", response_model=MobileApiResponse)
def logout(
    current_user: User = Depends(get_current_mobile_user)
):
    """User logout."""
    return MobileApiResponse(
        status=1,
        message="Logged out successfully",
        data={}
    )

@router.delete("/user/delete", response_model=MobileApiResponse)
def delete_account(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Delete or deactivate user account."""
    current_user.is_active = False
    db.commit()
    return MobileApiResponse(
        status=1,
        message="Account deleted successfully",
        data={}
    )
