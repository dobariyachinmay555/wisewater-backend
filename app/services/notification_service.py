import logging
from typing import List, Optional
import httpx
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.notification import Notification

logger = logging.getLogger(__name__)

async def broadcast_society_notification(
    db: Session,
    society_id: int,
    sender_id: int,
    title: str,
    message: str,
    notification_type: str = "ANNOUNCEMENT"
) -> Notification:
    """
    Saves a broadcast notification for the entire society and triggers push notifications.
    """
    # 1. Save notification record
    notif = Notification(
        society_id=society_id,
        user_id=None,  # Broadcast to all
        sender_id=sender_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # 2. Collect FCM tokens of members in society
    members = db.query(User).filter(
        User.society_id == society_id,
        User.is_active == True,
        User.fcm_token.isnot(None),
        User.fcm_token != ""
    ).all()

    tokens = [m.fcm_token for m in members if m.fcm_token]
    logger.info(f"Broadcasting notification '{title}' to {len(tokens)} devices in society {society_id}")

    return notif
