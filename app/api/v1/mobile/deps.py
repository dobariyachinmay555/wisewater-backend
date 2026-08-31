from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

security = HTTPBearer(auto_error=False)

def get_current_mobile_user(
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Extract and authenticate the mobile user from Bearer JWT token."""
    # If no token provided or default mock development fallback
    if not auth_credentials or not auth_credentials.credentials:
        # Fallback to User 1 (Super Admin Chairman) during local testing if no header is sent
        user = db.query(User).filter(User.id == 1).first()
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing"
        )
    
    token = auth_credentials.credentials.replace("Bearer ", "").strip()
    payload = decode_access_token(token)

    
    if not payload:
        # Check if it's the development mock token
        if token.startswith("mock_"):
            user = db.query(User).filter(User.id == 1).first()
            if user:
                return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
        
    user_id = payload.get("sub")
    user = None

    if not str(user_id).isdigit():
        temp_mobile = str(user_id).replace("temp_", "")
        user = db.query(User).filter(User.mobile_number == temp_mobile).first()
        if not user:
            print(f"[AUTH DIAGNOSTICS] Temp user sub '{user_id}' not found by mobile '{temp_mobile}'")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Registration incomplete. Please submit registration form."
            )
    else:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user and payload.get("mobile_number"):
            user = db.query(User).filter(User.mobile_number == str(payload.get("mobile_number"))).first()

    # Safe Diagnostic Logging
    has_token = bool(user and user.fcm_token and user.fcm_token.strip())
    token_len = len(user.fcm_token.strip()) if has_token else 0
    token_prefix = user.fcm_token.strip()[:15] + "..." if has_token else "NONE"

    print("=" * 60)
    print(f"[AUTH DIAGNOSTICS]")
    print(f"Authenticated User ID (from JWT sub): {user_id}")
    print(f"Authenticated User Role (from JWT): {payload.get('role')} (user_type: {payload.get('user_type')})")
    print(f"User Record Found in DB: {bool(user)}")
    if user:
        print(f"DB User ID: {user.id}, Mobile: {user.mobile_number}, Name: {user.name}")
        print(f"FCM Token Exists: {has_token} (Length: {token_len}, Prefix: {token_prefix})")
    print("=" * 60)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User ID {user_id} not found in database"
        )
    return user


def resolve_media_url(raw_url: Optional[str]) -> str:
    """Normalize any image/file URL to a fully qualified live HTTPS URL."""
    if not raw_url or not raw_url.strip():
        return ""
    url = raw_url.strip()
    # Strip local dev origins if present in legacy rows
    url = url.replace("http://127.0.0.1:8000", "").replace("http://localhost:8000", "")
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return f"https://wisewater-backend.onrender.com{url}"

def format_user_details(user: User) -> dict:
    """Format user to exact UserDetailsModel JSON expected by Flutter."""
    society_data = None
    if user.society:
        blocks_data = [
            {
                "block_id": b.id,
                "title": b.title,
                "total_flats": b.total_flats
            }
            for b in user.society.blocks
        ]
        society_data = {
            "apartment_id": user.society.id,
            "title": user.society.name,
            "address": user.society.address,
            "city": user.society.city,
            "zip_code": user.society.zip_code,
            "unit_price": float(user.society.unit_price),
            "property_category": user.society.property_category or "FLAT_APARTMENT",
            "registration_status": user.society.registration_status or "ACTIVE",
            "registration_id": user.society.registration_id,
            "total_houses": user.society.total_houses,
            "rejection_reason": user.society.rejection_reason,
            "change_request_notes": user.society.change_request_notes,
            "blocks": blocks_data
        }
        
    block_data = None
    if user.block:
        block_data = {
            "block_id": user.block.id,
            "title": user.block.title
        }

    appr_status = user.approval_status
    if user.user_type == 3 and user.society and (user.society.status == "ACTIVE" or user.society.registration_status == "ACTIVE"):
        appr_status = 1

    meter_img = ""
    if user.readings:
        sorted_readings = sorted(user.readings, key=lambda r: r.id, reverse=True)
        if sorted_readings and sorted_readings[0].image_url:
            meter_img = resolve_media_url(sorted_readings[0].image_url)

    return {
        "user_id": user.id,
        "name": user.name,
        "mobile_number": user.mobile_number,
        "email": user.email or "",
        "user_type": user.user_type,
        "apartment": society_data,
        "block": block_data,
        "flat_number": user.flat_number or "",
        "approval_status": appr_status,
        "previous_unit": user.previous_unit or 0,
        "initial_reading": user.previous_unit or 0,
        "meter_image": meter_img,
        "registration_status": user.society.registration_status if user.society else "DRAFT"
    }
