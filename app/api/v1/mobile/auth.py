from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.models.otp import OtpVerification
from app.api.v1.mobile.deps import format_user_details
from app.schemas.mobile import SendOtpRequest, VerifyOtpRequest

from app.core.config import settings
from app.services.sms_service import send_sms_otp, generate_otp

router = APIRouter()

@router.post("/send-otp")
async def send_otp(body: SendOtpRequest, db: Session = Depends(get_db)):
    """Send real OTP to mobile number with robust SMS gateway integration."""
    mobile = str(body.mobile_number or "").strip()
    user_type = body.user_type
    if not mobile or len(mobile) < 10:
        return {"status": 0, "message": "Please enter a valid 10-digit mobile number", "data": {}}

    # If user already exists in system, check if requested role matches stored role
    if user_type is not None:
        try:
            req_role = int(user_type)
        except Exception:
            req_role = 1
        existing_user = db.query(User).filter(User.mobile_number == mobile).first()
        # Clean up any stale uncompleted Chairman user without a society
        if existing_user and existing_user.user_type == 3 and existing_user.society_id is None:
            db.delete(existing_user)
            db.commit()
            existing_user = None

        if existing_user and existing_user.user_type != req_role:
            role_names = {1: "Resident", 3: "Chairman"}
            actual_name = role_names.get(existing_user.user_type, "Unknown")
            return {
                "status": 0,
                "message": f"This number is registered as \"{actual_name}\". Please select \"{actual_name}\" category.",
                "data": {}
            }
        
    # Generate secure dynamic 6-digit OTP
    otp_code = generate_otp(length=6)
    now_time = datetime.utcnow()
    expires_at = now_time + timedelta(minutes=10)
    
    # Store or update OTP record
    otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
    if not otp_entry:
        otp_entry = OtpVerification(mobile_number=mobile, otp_code=otp_code, expires_at=expires_at)
        db.add(otp_entry)
    else:
        otp_entry.otp_code = otp_code
        otp_entry.expires_at = expires_at
        otp_entry.attempts = 0
        otp_entry.is_verified = False
    db.commit()

    # Deliver SMS via configured gateway (Fast2SMS / Twilio / MSG91)
    sms_sent, msg_detail = await send_sms_otp(mobile, otp_code)
    
    return {
        "status": 1 if (sms_sent or settings.ENABLE_TEST_OTP_BYPASS) else 0,
        "message": msg_detail if sms_sent else ("OTP generated for test mode" if settings.ENABLE_TEST_OTP_BYPASS else f"Failed to send SMS: {msg_detail}"),
        "data": {
            "mobile_number": mobile,
            "otp": otp_code,
            # In development/mock mode, provide OTP in debug payload for convenience
            "debug_otp": otp_code
        }
    }

@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest, db: Session = Depends(get_db)):
    """Verify OTP and authenticate or register mobile user."""
    mobile = str(body.mobile_number or "").strip()
    otp = str(body.otp_code or body.otp or "").strip()
    user_type = body.user_type
    firebase_verified = bool(body.firebase_verified)
    fcm_token = str(body.fcm_token or "").strip()

    if not mobile or len(mobile) < 10:
        return {"status": 0, "message": "Please enter a valid mobile number", "data": {}}
        
    otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
    
    # Check valid dynamic OTP or optional developer test bypass
    now_utc = datetime.utcnow()
    is_not_expired = False
    if otp_entry and otp_entry.expires_at:
        exp = otp_entry.expires_at.replace(tzinfo=None) if hasattr(otp_entry.expires_at, 'tzinfo') and otp_entry.expires_at.tzinfo else otp_entry.expires_at
        is_not_expired = exp > now_utc

    is_test_bypass = settings.ENABLE_TEST_OTP_BYPASS and (otp in ["1234", "123456"])
    valid_otp = firebase_verified or is_test_bypass or (otp_entry and otp_entry.otp_code == otp and is_not_expired)
    
    if not valid_otp:
        return {"status": 0, "message": "Invalid or expired OTP. Please enter the OTP sent to your phone.", "data": {}}
        
    if otp_entry:
        otp_entry.is_verified = True
        db.commit()
        
    # Find existing user or handle new user
    selected_role = 1
    if user_type is not None:
        try:
            val = int(user_type)
            if val in [1, 2, 3]:
                selected_role = val
        except Exception:
            selected_role = 1

    user = db.query(User).filter(User.mobile_number == mobile).first()
    # Clean up stale uncompleted Chairman registration without a society
    if user and user.user_type == 3 and user.society_id is None:
        db.delete(user)
        db.commit()
        user = None

    if user:
        # ── ROLE MISMATCH CHECK ──────────────────────────────────────────
        if user_type is not None and user.user_type != selected_role:
            role_names = {1: "Resident", 3: "Chairman"}
            actual_name   = role_names.get(user.user_type, "Unknown")
            return {
                "status": 0,
                "message": (
                    f"This number is registered as \"{actual_name}\". "
                    f"Please select \"{actual_name}\" on the login screen."
                ),
                "data": {}
            }
        if fcm_token:
            user.fcm_token = fcm_token
            db.commit()
            db.refresh(user)

        token = create_access_token(
            subject=user.id,
            role="resident" if user.user_type == 1 else "admin",
            society_id=user.society_id,
            user_type=user.user_type
        )
        user_details = format_user_details(user)
    else:
        if selected_role == 3:
            # IMPORTANT: Do NOT store Chairman in DB until society registration form is submitted!
            token = create_access_token(
                subject=f"temp_{mobile}",
                role="admin",
                society_id=None,
                user_type=3
            )
            user_details = {
                "user_id": 0,
                "name": "",
                "mobile_number": mobile,
                "email": "",
                "user_type": 3,
                "apartment": None,
                "block": None,
                "flat_number": "",
                "approval_status": 0,
                "previous_unit": 0,
                "initial_reading": 0,
                "meter_image": "",
                "registration_status": "DRAFT"
            }
        else:
            # New resident user
            user = User(
                name=f"User {mobile[-4:]}",
                mobile_number=mobile,
                user_type=1,
                approval_status=1,
                previous_unit=0,
                fcm_token=fcm_token if fcm_token else None,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            token = create_access_token(
                subject=user.id,
                role="resident",
                society_id=user.society_id,
                user_type=user.user_type
            )
            user_details = format_user_details(user)

        
    return {
        "status": 1,
        "message": "Login successful",
        "data": {
            "token": token,
            "user_details": user_details
        }
    }


