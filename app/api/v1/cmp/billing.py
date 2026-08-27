from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.billing import Bill
from app.models.society import Society
from app.models.user import User
from app.api.v1.cmp.deps import get_current_staff

router = APIRouter()

@router.get("/bills")
def list_bills(
    society_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),  # PENDING, PAID, OVERDUE, CANCELLED
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """List bills across all societies."""
    query = db.query(Bill)
    
    if society_id:
        query = query.filter(Bill.society_id == society_id)
    if user_id:
        query = query.filter(Bill.user_id == user_id)
    if status and status.upper() != "ALL":
        query = query.filter(Bill.payment_status == status.upper())
        
    total = query.count()
    bills = query.order_by(Bill.id.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for b in bills:
        user = db.query(User).filter(User.id == b.user_id).first()
        society = db.query(Society).filter(Society.id == b.society_id).first()
        
        items.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "society_name": society.name if society else f"Society #{b.society_id}",
            "resident_name": user.name if user else f"User #{b.user_id}",
            "flat_number": user.flat_number if user else "N/A",
            "billing_month": b.billing_month,
            "billing_year": b.billing_year,
            "consumption_units": b.consumption_units,
            "unit_price": float(b.unit_price),
            "total_amount": float(b.total_amount),
            "due_date": b.due_date.strftime("%Y-%m-%d") if b.due_date else "",
            "payment_status": b.payment_status,
            "created_at": b.created_at.strftime("%Y-%m-%d") if b.created_at else ""
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }
