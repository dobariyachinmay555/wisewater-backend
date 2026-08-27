from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.audit import AuditLog
from app.api.v1.cmp.deps import get_current_staff

router = APIRouter()

@router.get("")
def list_audit_logs(
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_staff = Depends(get_current_staff),
    db: Session = Depends(get_db)
):
    """Immutable audit trail of all platform activities and admin interventions."""
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
        
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = [
        {
            "id": l.id,
            "actor_type": l.actor_type,
            "actor_id": l.actor_id,
            "actor_email": l.actor_email or "system",
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "society_id": l.society_id,
            "before_state": l.before_state,
            "after_state": l.after_state,
            "ip_address": l.ip_address or "127.0.0.1",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
        }
        for l in logs
    ]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit
    }
