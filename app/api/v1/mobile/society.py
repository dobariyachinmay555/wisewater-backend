import os
import uuid
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, Query, File, UploadFile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.society import Society, Block, Flat, House
from app.models.user import User
from app.models.reading import MeterReading
from app.schemas.mobile import (
    MobileApiResponse, UpdateApartmentDetailRequest, UpdateBlockTitleRequest, JoinSocietyRequest
)
from app.api.v1.mobile.deps import get_current_mobile_user, format_user_details

router = APIRouter()

@router.post("/upload-image", response_model=MobileApiResponse)
async def upload_image(
    image: UploadFile = File(...)
):
    """Upload photo (e.g. meter photo) and return public url."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_ext = os.path.splitext(image.filename)[1] if image.filename else ".jpg"
    file_name = f"meter_{uuid.uuid4().hex[:12]}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    rel_url = f"/uploads/{file_name}"
    full_url = f"http://127.0.0.1:8000{rel_url}"
    return MobileApiResponse(status=1, message="Image uploaded successfully", data={"image_url": rel_url, "full_url": full_url})


@router.get("/search-apartments", response_model=MobileApiResponse)
def search_apartments(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Search registered societies and return them with their block lists."""
    query = db.query(Society).filter(Society.status == "ACTIVE")
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.filter(
            (Society.name.ilike(search_term)) |
            (Society.city.ilike(search_term)) |
            (Society.address.ilike(search_term))
        )
    societies = query.all()
    
    result = []
    for soc in societies:
        blocks = [
            {"id": b.id, "block_id": b.id, "title": b.title, "total_flats": b.total_flats}
            for b in soc.blocks
        ]
        result.append({
            "id": soc.id,
            "apartment_id": soc.id,
            "name": soc.name,
            "title": soc.name,
            "address": soc.address,
            "city": soc.city,
            "zip_code": soc.zip_code,
            "unit_price": float(soc.unit_price),
            "blocks": blocks
        })
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/update-apartment-detail", response_model=MobileApiResponse)
def update_apartment_detail(
    payload: UpdateApartmentDetailRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Assign user to selected society, block, flat number, and name."""
    current_user.society_id = payload.apartment_id
    current_user.block_id = payload.block_id
    current_user.flat_number = payload.flat_number.strip()
    current_user.name = payload.name.strip()
    current_user.approval_status = 1  # Auto approve or set to 0 for strict societies
    db.commit()
    return MobileApiResponse(status=1, message="Apartment details updated successfully", data={})

@router.get("/apartment-blocks", response_model=MobileApiResponse)
def get_apartment_blocks(
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get all blocks for the authenticated user's society."""
    soc_id = current_user.society_id or 1
    blocks = db.query(Block).filter(Block.society_id == soc_id).all()
    result = [
        {"id": b.id, "block_id": b.id, "title": b.title, "total_flats": b.total_flats}
        for b in blocks
    ]
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/apartment-block/store-update", response_model=MobileApiResponse)
def update_block_title(
    payload: UpdateBlockTitleRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Update block title (Chairman only)."""
    block = db.query(Block).filter(Block.id == payload.block_id).first()
    if not block:
        return MobileApiResponse(status=0, message="Block not found", data={})
        
    block.title = payload.title.strip()
    db.commit()
    return MobileApiResponse(status=1, message="Block updated successfully", data={})

@router.get("/apartment-block/users", response_model=MobileApiResponse)
def get_block_users(
    block_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get all residents inside a specific block or entire society."""
    soc_id = current_user.society_id or 1
    query = db.query(User).filter(
        User.society_id == soc_id,
        User.is_active == True,
        User.approval_status == 1
    )
    if block_id is not None and block_id > 0:
        query = query.filter(User.block_id == block_id)
        
    users = query.order_by(User.id.asc()).all()
    
    result = [
        {
            "user_id": u.id,
            "name": u.name,
            "mobile_number": u.mobile_number,
            "flat_number": u.flat_number or "",
            "previous_unit": u.previous_unit or 0,
            "current_unit": u.previous_unit or 0,
            "user_type": u.user_type
        }
        for u in users
    ]
    return MobileApiResponse(status=1, message="Success", data=result)

@router.get("/society/by-code/{code}", response_model=MobileApiResponse)
def get_society_by_code(
    code: str,
    db: Session = Depends(get_db)
):
    """Retrieve full society structure by its code (e.g. SOC-1001 or TMP-XXXX)."""
    clean_code = code.strip().upper()
    soc = db.query(Society).filter(
        (Society.code == clean_code) |
        (Society.registration_id == clean_code)
    ).first()

    if not soc:
        return MobileApiResponse(status=0, message=f"No society found for code '{code}'", data={})

    blocks_data = [
        {
            "id": b.id,
            "block_id": b.id,
            "title": b.title,
            "total_flats": b.total_flats,
            "flats": [
                {"id": f.id, "flat_number": f.flat_number, "status": f.status}
                for f in b.flats
            ]
        }
        for b in soc.blocks
    ]

    houses_data = [
        {"id": h.id, "house_number": h.house_number, "status": h.status}
        for h in soc.houses
    ]

    return MobileApiResponse(
        status=1,
        message="Society details retrieved",
        data={
            "id": soc.id,
            "apartment_id": soc.id,
            "name": soc.name,
            "code": soc.code,
            "registration_id": soc.registration_id,
            "property_category": soc.property_category or "FLAT_APARTMENT",
            "address": soc.address,
            "city": soc.city,
            "state": soc.state,
            "zip_code": soc.zip_code,
            "unit_price": float(soc.unit_price) if soc.unit_price else 25.0,
            "total_blocks": len(soc.blocks),
            "total_flats": sum([b.total_flats for b in soc.blocks]) if soc.blocks else (soc.total_houses or 0),
            "total_houses": soc.total_houses or 0,
            "blocks": blocks_data,
            "houses": houses_data
        }
    )

@router.post("/society/join-request", response_model=MobileApiResponse)
def submit_join_society_request(
    payload: JoinSocietyRequest,
    db: Session = Depends(get_db)
):
    """Member submits request to join a society with flat or house number."""
    soc_id = payload.society_id
    if not soc_id and payload.society_code:
        clean_code = payload.society_code.strip().upper()
        soc = db.query(Society).filter(
            (Society.code == clean_code) |
            (Society.registration_id == clean_code)
        ).first()
        if soc:
            soc_id = soc.id

    if not soc_id:
        return MobileApiResponse(status=0, message="Please specify a valid society to join", data={})

    soc = db.query(Society).filter(Society.id == soc_id).first()
    if not soc:
        return MobileApiResponse(status=0, message="Society not found", data={})

    mobile = payload.mobile_number.strip()
    if not mobile or len(mobile) < 10:
        return MobileApiResponse(status=0, message="Please enter a valid 10-digit mobile number", data={})

    name = payload.name.strip()
    if not name:
        return MobileApiResponse(status=0, message="Please enter your name", data={})

    flat_or_house = (payload.flat_number or payload.house_number or "").strip()

    init_reading = payload.initial_reading or 0
    img_url = payload.image_url or ""

    # Find or create user
    user = db.query(User).filter(User.mobile_number == mobile).first()
    if not user:
        user = User(
            name=name,
            mobile_number=mobile,
            email=payload.email.strip() if payload.email else None,
            society_id=soc_id,
            block_id=payload.block_id,
            flat_number=flat_or_house,
            user_type=payload.role or 1,
            approval_status=0,  # Pending approval by Chairman
            previous_unit=init_reading,
            is_active=True
        )
        db.add(user)
    else:
        user.name = name
        user.society_id = soc_id
        user.block_id = payload.block_id
        user.flat_number = flat_or_house
        user.user_type = payload.role or 1
        user.approval_status = 0
        user.previous_unit = init_reading
        user.is_active = True
        if payload.email and payload.email.strip():
            user.email = payload.email.strip()

    db.commit()
    db.refresh(user)

    # Save initial baseline meter reading record if provided
    if init_reading > 0 or img_url:
        init_r = MeterReading(
            society_id=soc_id,
            user_id=user.id,
            block_id=user.block_id,
            previous_unit=0,
            current_unit=init_reading,
            total_unit=0,
            unit_price=float(soc.unit_price) if soc.unit_price else 25.0,
            total_price=0.0,
            image_url=img_url,
            status=0,  # Pending
            remarks="Initial Reading upon Joining",
            is_deletable=False
        )
        db.add(init_r)
        db.commit()

    from app.core.security import create_access_token
    token = create_access_token(
        subject=user.id,
        role="resident",
        society_id=soc.id,
        user_type=user.user_type
    )

    return MobileApiResponse(
        status=1,
        message="Join request submitted successfully. Awaiting Chairman approval.",
        data={
            "token": token,
            "user_details": format_user_details(user)
        }
    )
