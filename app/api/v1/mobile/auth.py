from datetime import datetime, timezone, timedelta
import secrets
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
from app.services.sms_service import send_sms_otp, generate_otp, normalize_indian_mobile

router = APIRouter()

@router.post("/send-otp")
async def send_otp(body: SendOtpRequest, db: Session = Depends(get_db)):
    """Send real 6-digit OTP to Indian mobile number via configured SMS gateway."""
    raw_mobile = str(body.mobile_number or "").strip()
    mobile = normalize_indian_mobile(raw_mobile)
    user_type = body.user_type
    
    if not mobile:
        return {
            "status": 0,
            "message": "Please enter a valid 10-digit Indian mobile number",
            "data": {}
        }

    # If user already exists in system, check if requested role matches stored role
    if user_type is not None:
        try:
            req_role = int(user_type)
        except Exception:
            req_role = 1
        existing_user = db.query(User).filter(User.mobile_number == mobile).first()
        if existing_user and existing_user.society_id is not None and existing_user.user_type != req_role:
            role_names = {1: "Resident", 3: "Chairman"}
            actual_name = role_names.get(existing_user.user_type, "Unknown")
            return {
                "status": 0,
                "message": f"This number is registered as \"{actual_name}\". Please select \"{actual_name}\" category.",
                "data": {}
            }
        
    # Generate secure dynamic 6-digit OTP
    otp_code = generate_otp(length=6)
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    
    # Invalidate previous OTP and store new active OTP record
    otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
    if not otp_entry:
        otp_entry = OtpVerification(
            mobile_number=mobile,
            otp_code=otp_code,
            expires_at=expires_at,
            attempts=0,
            is_verified=False
        )
        db.add(otp_entry)
    else:
        otp_entry.otp_code = otp_code
        otp_entry.expires_at = expires_at
        otp_entry.attempts = 0
        otp_entry.is_verified = False
        otp_entry.created_at = now_utc
    db.commit()

    # Deliver SMS via configured gateway (Fast2SMS / MSG91 / Twilio)
    sms_sent, msg_detail = await send_sms_otp(mobile, otp_code)
    
    if not sms_sent:
        if settings.ENABLE_TEST_OTP_BYPASS:
            return {
                "status": 1,
                "message": "OTP generated (test mode: use 1234)",
                "data": {
                    "mobile_number": mobile
                }
            }
        return {
            "status": 0,
            "message": msg_detail or "Unable to send OTP. Please try again.",
            "data": {}
        }
    
    return {
        "status": 1,
        "message": "OTP sent successfully to your mobile number",
        "data": {
            "mobile_number": mobile
        }
    }

@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest, db: Session = Depends(get_db)):
    """Verify OTP and authenticate or register mobile user."""
    raw_mobile = str(body.mobile_number or "").strip()
    mobile = normalize_indian_mobile(raw_mobile)
    otp = str(body.otp_code or body.otp or "").strip()
    user_type = body.user_type
    fcm_token = str(body.fcm_token or "").strip()

    if not mobile:
        return {"status": 0, "message": "Please enter a valid 10-digit Indian mobile number", "data": {}}
        
    is_test_bypass = settings.ENABLE_TEST_OTP_BYPASS and (otp in ["1234", "123456"])

    if not is_test_bypass:
        if not otp or len(otp) != 6 or not otp.isdigit():
            return {"status": 0, "message": "Please enter a valid 6-digit OTP", "data": {}}
            
        otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
        
        if not otp_entry:
            return {"status": 0, "message": "No OTP requested for this number. Please request an OTP first.", "data": {}}
            
        if otp_entry.is_verified:
            return {"status": 0, "message": "This OTP has already been used. Please request a new OTP.", "data": {}}
            
        if otp_entry.attempts >= settings.MAX_OTP_ATTEMPTS:
            return {"status": 0, "message": "Maximum verification attempts exceeded. Please request a new OTP.", "data": {}}

        now_utc = datetime.now(timezone.utc)
        exp = otp_entry.expires_at
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
            
        if exp and exp < now_utc:
            return {"status": 0, "message": "OTP has expired. Please request a new OTP.", "data": {}}

        # Validate OTP matching securely
        is_match = secrets.compare_digest(otp_entry.otp_code, otp)
        
        if not is_match:
            otp_entry.attempts += 1
            db.commit()
            remaining = settings.MAX_OTP_ATTEMPTS - otp_entry.attempts
            if remaining <= 0:
                return {"status": 0, "message": "Maximum verification attempts exceeded. Please request a new OTP.", "data": {}}
            return {
                "status": 0,
                "message": f"Invalid OTP. {remaining} attempt{'s' if remaining > 1 else ''} remaining.",
                "data": {}
            }
            
        # Mark OTP as verified to prevent reuse
        otp_entry.is_verified = True
        db.commit()
    else:
        otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
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

    if user:
        # ── ROLE MISMATCH CHECK (Only for registered society members) ─────────
        if user_type is not None and user.society_id is not None and user.user_type != selected_role:
            role_names = {1: "Resident", 3: "Chairman"}
            actual_name = role_names.get(user.user_type, "Unknown")
            return {
                "status": 0,
                "message": (
                    f"This number is registered as \"{actual_name}\". "
                    f"Please select \"{actual_name}\" on the login screen."
                ),
                "data": {}
            }
        
        # If user has not completed registration yet, allow role selection
        if user.society_id is None and user.user_type != selected_role:
            user.user_type = selected_role
            user.approval_status = 0 if selected_role == 3 else 1
            
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
        # Create new user record in DB
        user = User(
            name=f"Chairman {mobile[-4:]}" if selected_role == 3 else f"User {mobile[-4:]}",
            mobile_number=mobile,
            user_type=selected_role,
            approval_status=0 if selected_role == 3 else 1,
            previous_unit=0,
            fcm_token=fcm_token if fcm_token else None,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(
            subject=user.id,
            role="admin" if selected_role == 3 else "resident",
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


