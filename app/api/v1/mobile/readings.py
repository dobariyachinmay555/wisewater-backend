import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.reading import MeterReading
from app.models.society import Society
from app.models.billing import Bill
from app.schemas.mobile import MobileApiResponse, UpdatePreviousUnitRequest
from app.api.v1.mobile.deps import get_current_mobile_user, resolve_media_url
from app.services.billing_service import calculate_reading_bill, generate_bill_for_reading
from app.services.pdf_service import generate_water_bill_pdf

router = APIRouter()

@router.get("/get-unit-readings", response_model=MobileApiResponse)
def get_unit_readings(
    page: int = Query(1),
    apartment_user_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Get history of unit readings for a user or target resident."""
    target_user_id = current_user.id
    if apartment_user_id and apartment_user_id > 0:
        target_user_id = apartment_user_id
    
    target_user = db.query(User).filter(User.id == target_user_id).first()

    # If target user has an active flat assignment, include the flat's meter reading history
    # so reading history continues seamlessly for the incoming resident
    if target_user and target_user.flat_number and target_user.society_id:
        from app.models.meter import Meter
        meter = db.query(Meter).filter(
            Meter.society_id == target_user.society_id,
            Meter.block_id == target_user.block_id,
            Meter.flat_number == target_user.flat_number
        ).first()

        if meter:
            readings = db.query(MeterReading).filter(
                (MeterReading.user_id == target_user_id) |
                ((MeterReading.meter_id == meter.id) & (MeterReading.society_id == target_user.society_id))
            ).order_by(MeterReading.created_at.desc(), MeterReading.id.desc()).all()
        else:
            readings = db.query(MeterReading).filter(
                MeterReading.user_id == target_user_id
            ).order_by(MeterReading.created_at.desc(), MeterReading.id.desc()).all()
    else:
        readings = db.query(MeterReading).filter(
            MeterReading.user_id == target_user_id
        ).order_by(MeterReading.created_at.desc(), MeterReading.id.desc()).all()
    
    result = []
    for r in readings:
        created_str = r.created_at.strftime("%d %b %Y") if r.created_at else ""

        # If approved, attach or generate Bill
        bill_data = None
        if r.status == 1:
            bill = db.query(Bill).filter(Bill.reading_id == r.id).first()
            if not bill:
                try:
                    bill = generate_bill_for_reading(db, r)
                except Exception:
                    pass
            if bill:
                bill_data = {
                    "bill_id": bill.id,
                    "bill_number": bill.bill_number,
                    "billing_month": bill.billing_month,
                    "billing_year": bill.billing_year,
                    "consumption_units": bill.consumption_units,
                    "unit_price": float(bill.unit_price),
                    "total_amount": float(bill.total_amount),
                    "due_date": bill.due_date.strftime("%d %b %Y") if bill.due_date else "",
                    "payment_status": bill.payment_status or "UNPAID"
                }

        result.append({
            "user_unit_history_id": r.id,
            "previous_unit": r.previous_unit,
            "current_unit": r.current_unit,
            "total_unit": r.total_unit,
            "unit_price": float(r.unit_price),
            "total_price": float(r.total_price),
            "image": resolve_media_url(r.image_url),
            "status": r.status,  # 0: Pending, 1: Approved, 2: Rejected
            "remarks": r.remarks or ("Approved" if r.status == 1 else "Pending"),
            "created_at": created_str,
            "is_deletable": r.is_deletable,
            "bill": bill_data
        })
    return MobileApiResponse(status=1, message="Success", data=result)

@router.post("/store-unit-reading", response_model=MobileApiResponse)
async def store_unit_reading(
    unit: str = Form(...),
    image: Optional[UploadFile] = File(None),
    apartment_user_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Submit a water meter reading with image proof."""
    target_user = current_user
    if apartment_user_id and apartment_user_id.strip():
        target_user = db.query(User).filter(User.id == int(apartment_user_id)).first() or current_user
        
    try:
        current_unit_val = int(unit.strip())
    except ValueError:
        return MobileApiResponse(status=0, message="Invalid unit value", data={})
        
    previous_unit_val = target_user.previous_unit or 0
    society = target_user.society or db.query(Society).filter(Society.id == (target_user.society_id or 1)).first()
    unit_price_val = float(society.unit_price) if society else 25.00
    
    # Calculate consumption and cost
    try:
        total_unit, total_price = calculate_reading_bill(previous_unit_val, current_unit_val, unit_price_val)
    except ValueError as e:
        return MobileApiResponse(status=0, message=str(e), data={})
        
    # Save image file if provided
    image_url = ""
    if image:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        file_ext = os.path.splitext(image.filename)[1] if image.filename else ".jpg"
        file_name = f"meter_{uuid.uuid4().hex[:12]}{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/uploads/{file_name}"
        
    # Auto-approve if submitted by Admin / Chairman, else set Pending (0)
    is_admin = current_user.user_type in [2, 3]
    initial_status = 1 if is_admin else 0

    # Associate reading with physical meter if available
    meter = None
    if target_user.flat_number and target_user.society_id:
        from app.models.meter import Meter
        meter = db.query(Meter).filter(
            Meter.society_id == target_user.society_id,
            Meter.block_id == target_user.block_id,
            Meter.flat_number == target_user.flat_number
        ).first()
    
    reading = MeterReading(
        society_id=target_user.society_id or (society.id if society else 1),
        user_id=target_user.id,
        meter_id=meter.id if meter else None,
        block_id=target_user.block_id,
        previous_unit=previous_unit_val,
        current_unit=current_unit_val,
        total_unit=total_unit,
        unit_price=unit_price_val,
        total_price=total_price,
        image_url=image_url,
        status=initial_status,
        remarks="Approved" if initial_status == 1 else "Submitted from mobile",
        is_deletable=True
    )
    db.add(reading)
    
    # If auto-approved, update user's previous unit and meter's current reading
    if initial_status == 1:
        target_user.previous_unit = current_unit_val
        if meter:
            meter.current_reading = current_unit_val
        generate_bill_for_reading(db, reading)
        
    db.commit()
    db.refresh(reading)

    # Notify Society Chairman if submitted by resident for review
    if initial_status == 0 and target_user.society_id:
        try:
            from app.services.notification_service import notify_society_chairman
            flat_info = target_user.flat_number or "Unit"
            notify_society_chairman(
                db=db,
                society_id=target_user.society_id,
                title=f"New Meter Reading: {target_user.name} ({flat_info})",
                message=f"Resident submitted {current_unit_val} units (Consumed: {total_unit} units). Tap to review & approve.",
                notification_type="READING_REQUEST",
                data={"reading_id": str(reading.id), "user_id": str(target_user.id)},
                sender_id=target_user.id
            )
        except Exception as e:
            pass
    
    return MobileApiResponse(
        status=1,
        message="Reading saved successfully",
        data={"user_unit_history_id": reading.id}
    )

@router.delete("/delete-unit-reading/{id}", response_model=MobileApiResponse)
def delete_unit_reading(
    id: int,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Delete a reading if it's deletable."""
    reading = db.query(MeterReading).filter(MeterReading.id == id).first()
    if not reading:
        return MobileApiResponse(status=0, message="Reading not found", data={})
        
    db.delete(reading)
    db.commit()
    return MobileApiResponse(status=1, message="Deleted successfully", data={})

@router.post("/update-previous-unit", response_model=MobileApiResponse)
def update_previous_unit(
    payload: UpdatePreviousUnitRequest,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Set initial baseline meter unit for a resident."""
    user_id = int(payload.apartment_user_id) if payload.apartment_user_id else current_user.id
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return MobileApiResponse(status=0, message="User not found", data={})
        
    try:
        target_user.previous_unit = int(payload.unit.strip())
        db.commit()
        return MobileApiResponse(status=1, message="Previous unit set successfully", data={})
    except ValueError:
        return MobileApiResponse(status=0, message="Invalid unit value", data={})

@router.get("/download-reading-history-report", response_model=MobileApiResponse)
def download_reading_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    period_type: Optional[str] = Query("1_MONTH"),  # "1_MONTH" or "6_MONTHS"
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Download 1-Month or 6-Months water reading & consumption report in CSV format."""
    import csv
    soc_id = current_user.society_id or 1
    society = db.query(Society).filter(Society.id == soc_id).first()
    soc_name = society.name if society else "Society"
    soc_code = society.code if society else "SOC"

    # Query all users and readings for the society
    users = db.query(User).filter(
        User.society_id == soc_id,
        User.is_active == True,
        User.approval_status == 1
    ).order_by(User.flat_number.asc(), User.id.asc()).all()

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    report_tag = "6months" if period_type == "6_MONTHS" else "1month"
    filename = f"reading_report_{soc_code}_{report_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)

    total_consumption = 0
    total_revenue = 0.0

    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Header Metadata
        writer.writerow(["WiseWater - Water Consumption & Billing Report"])
        writer.writerow(["Society Name:", soc_name, "Society Code:", soc_code])
        writer.writerow(["Report Type:", "6 Months (Bi-Annual)" if period_type == "6_MONTHS" else "1 Month Monthly", "Generated At:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        if start_date and end_date:
            writer.writerow(["Date Range:", f"{start_date} to {end_date}"])
        writer.writerow([])  # Blank row

        # Table Column Headers
        writer.writerow([
            "Sl No", "Flat / House", "Resident Name", "Mobile Number", "Block",
            "Previous Reading", "Current Reading", "Consumed Units",
            "Rate per Unit (INR)", "Total Amount (INR)", "Status", "Reading Date"
        ])

        # Populate rows
        for idx, u in enumerate(users, start=1):
            latest_reading = db.query(MeterReading).filter(
                MeterReading.user_id == u.id
            ).order_by(MeterReading.id.desc()).first()

            prev_u = latest_reading.previous_unit if latest_reading else (u.previous_unit or 0)
            curr_u = latest_reading.current_unit if latest_reading else (u.previous_unit or 0)
            consumed = latest_reading.total_unit if latest_reading else max(0, curr_u - prev_u)
            rate = float(latest_reading.unit_price) if latest_reading else (float(society.unit_price) if society else 25.0)
            amount = float(latest_reading.total_price) if latest_reading else (consumed * rate)
            status_str = "Approved" if (latest_reading and latest_reading.status == 1) else ("Pending" if latest_reading else "Baseline")
            reading_date = latest_reading.created_at.strftime("%d-%m-%Y") if (latest_reading and latest_reading.created_at) else "N/A"
            block_title = u.block.title if u.block else ("Row House" if society and society.property_category == "ROW_HOUSE" else "Main Block")

            total_consumption += consumed
            total_revenue += amount

            writer.writerow([
                idx,
                u.flat_number or "N/A",
                u.name,
                u.mobile_number,
                block_title,
                prev_u,
                curr_u,
                consumed,
                f"{rate:.2f}",
                f"{amount:.2f}",
                status_str,
                reading_date
            ])

        # Summary Row
        writer.writerow([])
        writer.writerow(["", "", "", "", "TOTALS:", "", "", total_consumption, "", f"{total_revenue:.2f}", "", ""])

    rel_url = f"/uploads/{filename}"

    return MobileApiResponse(
        status=1,
        message=f"{'6-Months' if period_type == '6_MONTHS' else '1-Month'} report generated successfully",
        data={
            "file_url": rel_url,
            "filename": filename,
            "period_type": period_type,
            "total_members": len(users),
            "total_consumption": total_consumption,
            "total_revenue": round(total_revenue, 2)
        }
    )

@router.get("/download-bill-pdf/{reading_id}", response_model=MobileApiResponse)
def download_bill_pdf(
    reading_id: int,
    current_user: User = Depends(get_current_mobile_user),
    db: Session = Depends(get_db)
):
    """Generate and return PDF download URL for a specific approved water reading bill."""
    reading = db.query(MeterReading).filter(MeterReading.id == reading_id).first()
    if not reading:
        return MobileApiResponse(status=0, message="Reading not found", data={})
        
    user = db.query(User).filter(User.id == reading.user_id).first()
    if not user:
        return MobileApiResponse(status=0, message="Resident not found", data={})
        
    society = db.query(Society).filter(Society.id == reading.society_id).first()
    soc_name = society.name if society else "WiseWater Society"
    soc_code = society.code if society else f"SOC-{reading.society_id}"
    soc_addr = society.address if society else ""
    
    bill = db.query(Bill).filter(Bill.reading_id == reading.id).first()
    if not bill:
        bill = generate_bill_for_reading(db, reading)
        
    reading_date_str = reading.created_at.strftime("%d %b %Y") if reading.created_at else datetime.now().strftime("%d %b %Y")
    due_date_str = bill.due_date.strftime("%d %b %Y") if (bill and bill.due_date) else "15 Days"
    flat_str = f"{user.block.title} - {user.flat_number}" if (user.block and user.flat_number) else (user.flat_number or "N/A")
    
    rel_pdf_path = generate_water_bill_pdf(
        bill_number=bill.bill_number if bill else f"BILL-{reading.id}",
        society_name=soc_name,
        society_code=soc_code,
        society_address=soc_addr,
        resident_name=user.name or "Resident",
        flat_number=flat_str,
        mobile_number=user.mobile_number or "",
        reading_date=reading_date_str,
        due_date=due_date_str,
        previous_unit=reading.previous_unit,
        current_unit=reading.current_unit,
        consumed_units=reading.total_unit,
        unit_price=float(reading.unit_price),
        total_amount=float(reading.total_price),
        payment_status=bill.payment_status if bill else "UNPAID"
    )
    
    return MobileApiResponse(
        status=1,
        message="Bill PDF generated successfully",
        data={
            "file_url": rel_pdf_path,
            "filename": os.path.basename(rel_pdf_path),
            "bill_number": bill.bill_number if bill else f"BILL-{reading.id}"
        }
    )
