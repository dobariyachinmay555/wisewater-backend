from decimal import Decimal
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.models.society import Society

def calculate_reading_bill(previous_unit: int, current_unit: int, unit_price: float) -> tuple[int, float]:
    """
    Validate and calculate water consumption units and cost.
    Validates current_unit >= previous_unit to prevent negative consumption.
    """
    if current_unit < previous_unit:
        raise ValueError(f"Current unit ({current_unit}) cannot be less than previous unit ({previous_unit})")
    
    total_unit = current_unit - previous_unit
    total_price = float(Decimal(str(total_unit)) * Decimal(str(unit_price)))
    return total_unit, total_price

def generate_bill_for_reading(db: Session, reading: MeterReading) -> Bill:
    """Generate and store a Bill from an approved MeterReading."""
    # Check if bill already exists for this reading
    existing_bill = db.query(Bill).filter(Bill.reading_id == reading.id).first()
    if existing_bill:
        return existing_bill
        
    society = db.query(Society).filter(Society.id == reading.society_id).first()
    soc_code = society.code if society else f"SOC-{reading.society_id}"
    
    month = reading.created_at.month if reading.created_at else date.today().month
    year = reading.created_at.year if reading.created_at else date.today().year
    
    bill_number = f"BILL-{year}{month:02d}-{soc_code}-{reading.user_id}-{reading.id}"
    
    bill = Bill(
        bill_number=bill_number,
        society_id=reading.society_id,
        user_id=reading.user_id,
        reading_id=reading.id,
        billing_month=month,
        billing_year=year,
        consumption_units=reading.total_unit,
        unit_price=reading.unit_price,
        total_amount=reading.total_price,
        due_date=date.today() + timedelta(days=15),
        payment_status="PENDING"
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill
