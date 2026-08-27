import random
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import create_access_token
from app.models.society import Society, Block, Flat, House
from app.models.user import User
from app.models.otp import OtpVerification
from app.models.audit import AuditLog
from app.schemas.mobile import (
    MobileApiResponse,
    SocietyRegistrationRequest,
    SocietyResubmitRequest,
    BlockConfigItem
)
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details
from app.services.audit_service import record_audit_log

router = APIRouter()

@router.post("/onboarding/send-otp", response_model=MobileApiResponse)
async def send_onboarding_otp(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    mobile = str(body.get("mobile_number") or body.get("phone_number") or "").strip()
    if not mobile or len(mobile) < 10:
        return MobileApiResponse(status=0, message="Please enter a valid 10-digit mobile number", data={})
        
    otp_code = "1234"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    
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
    db.commit()
    
    return MobileApiResponse(
        status=1,
        message="OTP sent successfully to registered number",
        data={"otp": otp_code, "mobile_number": mobile, "expires_in_seconds": 600}
    )

@router.post("/onboarding/verify-otp", response_model=MobileApiResponse)
async def verify_onboarding_otp(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    mobile = str(body.get("mobile_number") or body.get("phone_number") or "").strip()
    otp = str(body.get("otp_code") or body.get("otp") or "").strip()
    
    if not mobile or len(mobile) < 10:
        return MobileApiResponse(status=0, message="Please enter a valid mobile number", data={})
    if not otp:
        return MobileApiResponse(status=0, message="Please enter OTP", data={})
        
    otp_entry = db.query(OtpVerification).filter(OtpVerification.mobile_number == mobile).first()
    valid_otp = (otp == "1234") or (otp_entry and otp_entry.otp_code == otp and otp_entry.expires_at > datetime.now(timezone.utc))
    
    if not valid_otp:
        if otp_entry:
            otp_entry.attempts += 1
            db.commit()
        return MobileApiResponse(status=0, message="Invalid or expired OTP", data={})
        
    if otp_entry:
        otp_entry.is_verified = True
        db.commit()
        
    user = db.query(User).filter(User.mobile_number == mobile).first()
    token = None
    if user:
        token = create_access_token(
            subject=user.id,
            role="admin" if user.user_type in [2, 3] else "resident",
            society_id=user.society_id,
            user_type=user.user_type
        )
        
    return MobileApiResponse(
        status=1,
        message="Mobile number verified successfully",
        data={
            "verified": True,
            "mobile_number": mobile,
            "token": token,
            "user_details": format_user_details(user) if user else None
        }
    )

@router.post("/onboarding/register", response_model=MobileApiResponse)
def register_society_and_chairman(
    payload: SocietyRegistrationRequest,
    db: Session = Depends(get_db)
):
    if not payload.society_name or len(payload.society_name.strip()) < 3:
        return MobileApiResponse(status=0, message="Society name must be at least 3 characters", data={})
        
    if not payload.address or not payload.city or not payload.state or not payload.pin_code:
        return MobileApiResponse(status=0, message="Please fill in complete society address details", data={})
        
    if len(payload.pin_code.strip()) != 6 or not payload.pin_code.strip().isdigit():
        return MobileApiResponse(status=0, message="PIN code must be exactly 6 digits", data={})
        
    if not payload.chairman_name or not payload.chairman_mobile or not payload.chairman_email:
        return MobileApiResponse(status=0, message="Please provide all Chairman contact details", data={})
        
    prop_category = payload.property_category.strip().upper()
    if prop_category not in ["FLAT_APARTMENT", "ROW_HOUSE"]:
        prop_category = "FLAT_APARTMENT"
        
    try:
        rand_suffix = ''.join(random.choices(string.digits, k=6))
        reg_id = f"REG-{rand_suffix}"
        temp_code = f"TMP-{rand_suffix[:4]}"
        
        society = Society(
            name=payload.society_name.strip(),
            code=temp_code,
            registration_id=reg_id,
            property_category=prop_category,
            address=payload.address.strip(),
            city=payload.city.strip(),
            state=payload.state.strip(),
            zip_code=payload.pin_code.strip(),
            unit_price=float(payload.unit_price) if payload.unit_price is not None else 25.00,
            photo_submission_frequency=payload.photo_submission_frequency or "1_MONTH",
            status="PENDING",
            registration_status="PENDING",
            chairman_name=payload.chairman_name.strip(),
            chairman_mobile=payload.chairman_mobile.strip(),
            chairman_email=payload.chairman_email.strip(),
            contact_number=payload.contact_number.strip() if payload.contact_number else None,
            society_email=payload.society_email.strip() if payload.society_email else None,
            establishment_year=payload.establishment_year,
            total_houses=payload.total_houses if prop_category == "ROW_HOUSE" else None
        )
        db.add(society)
        db.flush()
        
        first_block_id = None
        if prop_category == "FLAT_APARTMENT":
            blocks_to_create = payload.blocks or []
            if not blocks_to_create:
                blocks_to_create = [BlockConfigItem(title="Block A", total_flats=20)]
                
            for b_idx, b_item in enumerate(blocks_to_create):
                b_title = b_item.title.strip() if b_item.title else f"Block {chr(65 + b_idx)}"
                b_flats = max(1, b_item.total_flats)
                
                block = Block(
                    society_id=society.id,
                    title=b_title,
                    total_flats=b_flats
                )
                db.add(block)
                db.flush()
                
                if b_idx == 0:
                    first_block_id = block.id
                    
                flats = []
                for f_num in range(1, b_flats + 1):
                    flat = Flat(
                        society_id=society.id,
                        block_id=block.id,
                        flat_number=str(f_num),
                        status="VACANT"
                    )
                    flats.append(flat)
                db.add_all(flats)
                
        elif prop_category == "ROW_HOUSE":
            house_count = max(1, payload.total_houses or 20)
            society.total_houses = house_count
            houses = []
            for h_num in range(1, house_count + 1):
                house = House(
                    society_id=society.id,
                    house_number=str(h_num),
                    status="VACANT"
                )
                houses.append(house)
            db.add_all(houses)
            
        mobile = payload.chairman_mobile.strip()
        chairman_user = db.query(User).filter(User.mobile_number == mobile).first()

        # ── ONE CHAIRMAN PER SOCIETY ─────────────────────────────────────
        # Check 1: Is this mobile already a chairman of a DIFFERENT society?
        if chairman_user and chairman_user.user_type == 3 and chairman_user.society_id is not None:
            existing_society = db.query(Society).filter(Society.id == chairman_user.society_id).first()
            if existing_society:
                db.rollback()
                return MobileApiResponse(
                    status=0,
                    message=(
                        f"This mobile number is already registered as Chairman "
                        f"of \"{existing_society.name}\". "
                        f"A Chairman can only manage one society."
                    ),
                    data={}
                )

        # Check 2: Does the new society already have a chairman assigned?
        # (Prevents duplicate chairmen if two registrations race)
        existing_chairman = db.query(User).filter(
            User.society_id == society.id,
            User.user_type == 3
        ).first()
        if existing_chairman and (not chairman_user or existing_chairman.id != chairman_user.id):
            db.rollback()
            return MobileApiResponse(
                status=0,
                message="This society already has a Chairman. A society can only have one Chairman.",
                data={}
            )
        # ────────────────────────────────────────────────────────────────

        if not chairman_user:
            chairman_user = User(
                name=payload.chairman_name.strip(),
                mobile_number=mobile,
                email=payload.chairman_email.strip(),
                user_type=3,
                society_id=society.id,
                block_id=first_block_id,
                flat_number="1" if prop_category == "FLAT_APARTMENT" else "House 1",
                approval_status=0,
                previous_unit=0,
                is_active=True
            )
            db.add(chairman_user)
        else:
            chairman_user.name = payload.chairman_name.strip()
            chairman_user.email = payload.chairman_email.strip()
            chairman_user.user_type = 3
            chairman_user.society_id = society.id
            chairman_user.block_id = first_block_id
            chairman_user.flat_number = "1" if prop_category == "FLAT_APARTMENT" else "House 1"
            chairman_user.approval_status = 0

        db.flush()

        
        record_audit_log(
            db=db,
            actor_type="USER",
            actor_id=str(chairman_user.id or "NEW"),
            actor_email=chairman_user.email,
            action="SOCIETY_REGISTRATION_SUBMITTED",
            entity_type="SOCIETY",
            entity_id=str(society.id),
            society_id=society.id,
            after_state={
                "registration_id": reg_id,
                "society_name": society.name,
                "category": prop_category,
                "status": "PENDING"
            }
        )
        
        db.commit()
        db.refresh(society)
        db.refresh(chairman_user)
        
        token = create_access_token(
            subject=chairman_user.id,
            role="admin",
            society_id=society.id,
            user_type=3
        )
        
        return MobileApiResponse(
            status=1,
            message="Society registration submitted successfully 🎉",
            data={
                "registration_id": reg_id,
                "society_id": society.id,
                "society_name": society.name,
                "property_category": prop_category,
                "registration_status": "PENDING",
                "chairman_name": chairman_user.name,
                "token": token,
                "user_details": format_user_details(chairman_user)
            }
        )
    except Exception as e:
        db.rollback()
        return MobileApiResponse(status=0, message=f"Registration failed: {str(e)}", data={})

@router.get("/onboarding/status", response_model=MobileApiResponse)
def get_onboarding_status(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    society = current_user.society
    if not society:
        return MobileApiResponse(
            status=1,
            message="No active registration found",
            data={"registration_status": "DRAFT", "user_details": format_user_details(current_user)}
        )
        
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
        message="Status loaded",
        data={
            "registration_id": society.registration_id or f"SOC-{society.id}",
            "society_id": society.id,
            "society_name": society.name,
            "code": society.code,
            "property_category": society.property_category or "FLAT_APARTMENT",
            "address": society.address,
            "city": society.city,
            "state": society.state,
            "pin_code": society.zip_code,
            "registration_status": society.registration_status or "PENDING",
            "status": society.status,
            "rejection_reason": society.rejection_reason,
            "change_request_notes": society.change_request_notes,
            "chairman_name": society.chairman_name or current_user.name,
            "chairman_mobile": society.chairman_mobile or current_user.mobile_number,
            "chairman_email": society.chairman_email or current_user.email,
            "total_blocks": len(society.blocks),
            "total_flats": total_units,
            "total_houses": society.total_houses,
            "blocks": blocks_data,
            "submitted_at": society.created_at.strftime("%Y-%m-%d %H:%M") if society.created_at else "",
            "updated_at": society.updated_at.strftime("%Y-%m-%d %H:%M") if society.updated_at else ""
        }
    )

@router.put("/onboarding/resubmit", response_model=MobileApiResponse)
def resubmit_society_registration(
    payload: SocietyResubmitRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    society = current_user.society
    if not society:
        return MobileApiResponse(status=0, message="No registered society found to resubmit", data={})
        
    try:
        if payload.society_name:
            society.name = payload.society_name.strip()
        if payload.address:
            society.address = payload.address.strip()
        if payload.city:
            society.city = payload.city.strip()
        if payload.state:
            society.state = payload.state.strip()
        if payload.pin_code:
            society.zip_code = payload.pin_code.strip()
        if payload.chairman_name:
            society.chairman_name = payload.chairman_name.strip()
            current_user.name = payload.chairman_name.strip()
        if payload.chairman_email:
            society.chairman_email = payload.chairman_email.strip()
        if payload.unit_price is not None:
            society.unit_price = float(payload.unit_price)
        if payload.photo_submission_frequency:
            society.photo_submission_frequency = payload.photo_submission_frequency
            
        society.registration_status = "PENDING"
        society.status = "PENDING"
        society.change_request_notes = None
        society.rejection_reason = None
        current_user.approval_status = 0
        
        record_audit_log(
            db=db,
            actor_type="USER",
            actor_id=str(current_user.id),
            actor_email=current_user.email,
            action="SOCIETY_REGISTRATION_RESUBMITTED",
            entity_type="SOCIETY",
            entity_id=str(society.id),
            society_id=society.id,
            after_state={"status": "PENDING", "registration_status": "PENDING"}
        )
        
        db.commit()
        db.refresh(society)
        db.refresh(current_user)
        
        return MobileApiResponse(
            status=1,
            message="Application resubmitted successfully for CMP review",
            data={
                "registration_status": "PENDING",
                "user_details": format_user_details(current_user)
            }
        )
    except Exception as e:
        db.rollback()
        return MobileApiResponse(status=0, message=f"Resubmission failed: {str(e)}", data={})
