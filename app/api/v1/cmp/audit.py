from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, String, or_
from app.core.database import get_db
from app.models.audit import AuditLog
from app.models.society import Society
from app.api.v1.cmp.deps import get_current_staff

router = APIRouter()

@router.get("")
def list_audit_logs(
    society_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    actor_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """Immutable audit trail of all platform activities and admin interventions."""
    query = db.query(AuditLog)
    
    if society_id is not None:
        query = query.filter(AuditLog.society_id == society_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)

    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            query = query.filter(AuditLog.created_at >= sd)
        except Exception:
            pass

    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            query = query.filter(AuditLog.created_at <= ed)
        except Exception:
            pass

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AuditLog.actor_email.ilike(term),
                AuditLog.actor_id.ilike(term),
                AuditLog.entity_id.ilike(term),
                AuditLog.action.ilike(term),
                cast(AuditLog.after_state, String).ilike(term),
                cast(AuditLog.before_state, String).ilike(term)
            )
        )
        
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    # Pre-fetch societies for enrichment
    soc_ids = set([l.society_id for l in logs if l.society_id])
    societies_map = {}
    if soc_ids:
        soc_records = db.query(Society).filter(Society.id.in_(soc_ids)).all()
        societies_map = {s.id: s.name for s in soc_records}

    items = []
    for l in logs:
        after = l.after_state if isinstance(l.after_state, dict) else {}
        before = l.before_state if isinstance(l.before_state, dict) else {}

        old_member = after.get("old_member") or (before if l.action in ["MEMBER_REPLACED", "MEMBER_REMOVED"] else None)
        new_member = after.get("new_member")

        old_member_name = old_member.get("name") if isinstance(old_member, dict) else (before.get("name") or before.get("old_member_name"))
        old_member_mobile = old_member.get("mobile_number") if isinstance(old_member, dict) else (before.get("mobile_number") or before.get("old_member_mobile"))
        
        new_member_name = new_member.get("name") if isinstance(new_member, dict) else (after.get("new_member_name") or ("VACANT" if l.action == "MEMBER_REMOVED" else None))
        new_member_mobile = new_member.get("mobile_number") if isinstance(new_member, dict) else (after.get("new_member_mobile") or ("N/A" if l.action == "MEMBER_REMOVED" else None))

        flat_number = after.get("flat_number") or before.get("flat_number") or (l.entity_id if l.entity_type == "FLAT" else "")
        block_title = after.get("block_title") or before.get("block_title") or ""
        meter_reading = after.get("meter_reading") or after.get("starting_meter_reading") or before.get("final_meter_reading")
        new_starting_reading = after.get("new_starting_reading") or meter_reading
        performed_by_name = after.get("performed_by_name") or l.actor_email or "Administrator"
        performed_by_role = after.get("performed_by_role") or ("Chairman" if l.actor_type == "USER" else l.actor_type)
        reason = after.get("reason") or "N/A"

        change_summary = ""
        if l.action == "MEMBER_REPLACED":
            change_summary = f"{old_member_name or 'Old Member'} → {new_member_name or 'New Member'}"
        elif l.action == "MEMBER_REMOVED":
            change_summary = f"{old_member_name or 'Old Member'} → VACANT"

        soc_name = societies_map.get(l.society_id) or after.get("society_name") or "Platform / General"

        items.append({
            "id": l.id,
            "actor_type": l.actor_type,
            "actor_id": l.actor_id,
            "actor_email": l.actor_email or "system",
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "society_id": l.society_id,
            "society_name": soc_name,
            "before_state": l.before_state,
            "after_state": l.after_state,
            "ip_address": l.ip_address or "127.0.0.1",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "",
            "formatted_date": l.created_at.strftime("%d %b %Y, %I:%M %p") if l.created_at else "",
            # Structured fields for easy UI presentation without reading raw JSON
            "change_summary": change_summary,
            "old_member_name": old_member_name,
            "old_member_mobile": old_member_mobile,
            "new_member_name": new_member_name,
            "new_member_mobile": new_member_mobile,
            "flat_number": flat_number,
            "block_title": block_title,
            "meter_reading": meter_reading,
            "new_starting_reading": new_starting_reading,
            "performed_by_name": performed_by_name,
            "performed_by_role": performed_by_role,
            "reason": reason
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }

