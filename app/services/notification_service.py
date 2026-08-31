import os
import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import settings, BACKEND_DIR
from app.models.user import User
from app.models.notification import Notification, NotificationRead

logger = logging.getLogger(__name__)

_firebase_initialized = False



def _get_firebase_app():
    """
    Initializes and returns the Firebase Admin App instance safely.
    Supports credentials from JSON file, raw JSON string in env,
    or Google Application Default Credentials.
    """
    global _firebase_initialized
    if _firebase_initialized and firebase_admin._apps:
        return firebase_admin.get_app()

    try:
        # 1. Try raw JSON credentials from environment variable
        if settings.FIREBASE_CREDENTIALS_JSON and settings.FIREBASE_CREDENTIALS_JSON.strip():
            try:
                cert_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
                cred = credentials.Certificate(cert_dict)
                firebase_admin.initialize_app(cred)
                _firebase_initialized = True
                logger.info("Firebase Admin initialized successfully using FIREBASE_CREDENTIALS_JSON.")
                return firebase_admin.get_app()
            except Exception as e:
                logger.warning(f"Failed to initialize Firebase with FIREBASE_CREDENTIALS_JSON: {e}")

        # 2. Try file path from settings or standard default location
        candidate_paths = []
        if settings.FIREBASE_CREDENTIALS_PATH and settings.FIREBASE_CREDENTIALS_PATH.strip():
            candidate_paths.append(settings.FIREBASE_CREDENTIALS_PATH)
            candidate_paths.append(os.path.join(BACKEND_DIR, settings.FIREBASE_CREDENTIALS_PATH))

        # Default standard file in backend root
        candidate_paths.append(os.path.join(BACKEND_DIR, "firebase-service-account.json"))
        candidate_paths.append(os.path.join(BACKEND_DIR, "serviceAccountKey.json"))

        for path in candidate_paths:
            if os.path.exists(path):
                try:
                    cred = credentials.Certificate(path)
                    firebase_admin.initialize_app(cred)
                    _firebase_initialized = True
                    logger.info(f"Firebase Admin initialized successfully using credentials file: {path}")
                    return firebase_admin.get_app()
                except Exception as e:
                    logger.warning(f"Failed to initialize Firebase with file {path}: {e}")

        # 3. Try default application credentials
        try:
            firebase_admin.initialize_app()
            _firebase_initialized = True
            logger.info("Firebase Admin initialized using default application credentials.")
            return firebase_admin.get_app()
        except Exception:
            logger.info("Firebase Admin credentials not found. Push notifications will be logged in fallback mode.")
            return None

    except Exception as e:
        logger.error(f"Error during Firebase Admin initialization: {e}")
        return None


def send_fcm_multicast(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Sends an FCM push notification to multiple device tokens via Firebase HTTP v1 API.
    Handles chunking (500 per batch) and auto-cleans stale/invalid tokens.
    """
    clean_tokens = list(set([str(t).strip() for t in tokens if t and str(t).strip()]))
    if not clean_tokens:
        return {"success_count": 0, "failure_count": 0, "invalid_tokens": []}

    # Ensure all data values are strings for FCM
    data_payload: Dict[str, str] = {}
    if data:
        for k, v in data.items():
            data_payload[str(k)] = str(v) if v is not None else ""
    data_payload["click_action"] = "FLUTTER_NOTIFICATION_CLICK"

    app = _get_firebase_app()
    if not app:
        logger.info(f"[FCM Fallback / Mock] Notification '{title}' not sent via FCM (credentials not loaded). Tokens: {len(clean_tokens)}")
        return {"success_count": 0, "failure_count": 0, "invalid_tokens": []}

    # Android specific notification options for heads-up alerts & sound
    android_config = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id="wisewater_notifications",
            sound="default",
            default_sound=True,
            default_vibrate_timings=True,
            icon="@mipmap/ic_launcher"
        )
    )


    # iOS APNs options
    apns_config = messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound="default",
                badge=1,
                content_available=True
            )
        )
    )


    notification = messaging.Notification(title=title, body=body)

    total_success = 0
    total_failure = 0
    invalid_tokens = []

    # Firebase send_each_for_multicast allows up to 500 tokens per batch
    batch_size = 500
    for i in range(0, len(clean_tokens), batch_size):
        chunk = clean_tokens[i:i + batch_size]
        message = messaging.MulticastMessage(
            tokens=chunk,
            notification=notification,
            data=data_payload,
            android=android_config,
            apns=apns_config
        )

        try:
            response = messaging.send_each_for_multicast(message, app=app)
            total_success += response.success_count
            total_failure += response.failure_count

            if response.failure_count > 0:
                for idx, res in enumerate(response.responses):
                    if not res.success:
                        err_code = str(res.exception)
                        failed_token = chunk[idx]
                        logger.warning(f"Failed to send FCM to token {failed_token[:15]}...: {err_code}")
                        print(f"[FCM ERROR] Token {failed_token[:15]}... Failed: {err_code}")
                        if res.exception and hasattr(res.exception, 'code'):
                            print(f"[FCM ERROR CODE] {res.exception.code}")
                            if res.exception.code in ['UNREGISTERED', 'INVALID_ARGUMENT']:
                                invalid_tokens.append(failed_token)
        except Exception as e:
            logger.error(f"Error sending multicast FCM batch: {e}")
            print(f"[FCM CRITICAL ERROR] {e}")
            total_failure += len(chunk)

    # Clean up stale/invalid tokens in DB if session provided
    if invalid_tokens and db:
        try:
            db.query(User).filter(User.fcm_token.in_(invalid_tokens)).update(
                {User.fcm_token: None},
                synchronize_session=False
            )
            db.commit()
            logger.info(f"Cleaned up {len(invalid_tokens)} stale FCM tokens from database.")
        except Exception as e:
            logger.warning(f"Failed to clean up stale tokens: {e}")

    logger.info(f"FCM Push Result for '{title}': {total_success} success, {total_failure} failure.")
    print(f"FCM messages sent: {len(clean_tokens)}")
    print(f"FCM success: {total_success}")
    print(f"FCM failure: {total_failure}")
    return {
        "success_count": total_success,
        "failure_count": total_failure,
        "invalid_tokens": invalid_tokens
    }



def test_single_fcm(
    db: Session,
    user_id: Optional[int] = None,
    mobile: Optional[str] = None,
    token: Optional[str] = None,
    title: str = "FCM Test",
    body: str = "Testing Firebase push notification"
) -> Dict[str, Any]:
    """
    Sends a test FCM push notification directly to ONE specific user or device token.
    Provides complete diagnostic logs and error reporting.
    """
    target_token = ""
    target_user = None

    if token and token.strip():
        target_token = token.strip()
    elif user_id:
        target_user = db.query(User).filter(User.id == user_id).first()
        if target_user and target_user.fcm_token:
            target_token = target_user.fcm_token.strip()
    elif mobile:
        target_user = db.query(User).filter(User.mobile_number == mobile.strip()).first()
        if target_user and target_user.fcm_token:
            target_token = target_user.fcm_token.strip()

    if not target_token:
        return {
            "status": 0,
            "message": "No valid FCM token found for specified user/device.",
            "diagnostics": {
                "user_found": bool(target_user),
                "user_id": target_user.id if target_user else user_id,
                "has_fcm_token": bool(target_user and target_user.fcm_token)
            }
        }

    app = _get_firebase_app()
    if not app:
        return {
            "status": 0,
            "message": "Firebase Admin SDK initialization failed or credentials not found.",
            "diagnostics": {"firebase_initialized": False}
        }

    # Send test message using HTTP v1 API
    android_config = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id="wisewater_notifications",
            sound="default",
            default_sound=True,
            default_vibrate_timings=True,
            icon="@mipmap/ic_launcher"
        )
    )

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={"type": "FCM_TEST", "click_action": "FLUTTER_NOTIFICATION_CLICK"},
        android=android_config,
        token=target_token
    )

    try:
        response = messaging.send(message, app=app)
        logger.info(f"Test FCM send SUCCESS to token {target_token[:15]}... Message ID: {response}")
        return {
            "status": 1,
            "message": "FCM test notification sent successfully to Firebase!",
            "diagnostics": {
                "message_id": response,
                "token_length": len(target_token),
                "token_prefix": target_token[:15] + "...",
                "user_id": target_user.id if target_user else None
            }
        }
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Test FCM send FAILED: {err_msg}")
        return {
            "status": 0,
            "message": f"Firebase send error: {err_msg}",
            "diagnostics": {
                "error_type": type(e).__name__,
                "token_length": len(target_token),
                "token_prefix": target_token[:15] + "..."
            }
        }



def send_user_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "ANNOUNCEMENT",
    data: Optional[Dict[str, Any]] = None,
    sender_id: Optional[int] = None
) -> Optional[Notification]:
    """
    Creates an in-app database notification for a single user and sends a targeted FCM push notification.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    # 1. Save database notification record
    notif = Notification(
        society_id=user.society_id,
        user_id=user.id,
        sender_id=sender_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # 2. Trigger FCM push notification if user has registered device token
    if user.fcm_token and user.fcm_token.strip():
        payload_data = data.copy() if data else {}
        payload_data.update({
            "notification_id": str(notif.id),
            "notification_type": notification_type,
            "user_id": str(user_id)
        })
        send_fcm_multicast(
            tokens=[user.fcm_token],
            title=title,
            body=message,
            data=payload_data,
            db=db
        )

    return notif


def notify_society_chairman(
    db: Session,
    society_id: int,
    title: str,
    message: str,
    notification_type: str = "ANNOUNCEMENT",
    data: Optional[Dict[str, Any]] = None,
    sender_id: Optional[int] = None
) -> List[Notification]:
    """
    Sends in-app notification and FCM push notification to all committee admins / chairman of a society.
    """
    if not society_id:
        return []

    chairmen = db.query(User).filter(
        User.society_id == society_id,
        User.user_type.in_([2, 3]),  # 2: Committee Admin, 3: Chairman
        User.is_active == True
    ).all()

    created_notifs = []
    fcm_tokens = []

    for admin in chairmen:
        notif = Notification(
            society_id=society_id,
            user_id=admin.id,
            sender_id=sender_id,
            title=title,
            message=message,
            notification_type=notification_type,
            is_read=False
        )
        db.add(notif)
        created_notifs.append(notif)
        if admin.fcm_token and admin.fcm_token.strip():
            fcm_tokens.append(admin.fcm_token.strip())

    db.commit()

    if fcm_tokens:
        payload_data = data.copy() if data else {}
        payload_data.update({
            "notification_type": notification_type,
            "society_id": str(society_id)
        })
        send_fcm_multicast(
            tokens=fcm_tokens,
            title=title,
            body=message,
            data=payload_data,
            db=db
        )

    return created_notifs


async def broadcast_society_notification(
    db: Session,
    society_id: int,
    sender_id: int,
    title: str,
    message: str,
    notification_type: str = "ANNOUNCEMENT",
    data: Optional[Dict[str, Any]] = None
) -> Notification:
    """
    Saves a broadcast notification for the entire society and triggers FCM push notifications to all residents.
    """
    # 1. Save notification record
    notif = Notification(
        society_id=society_id,
        user_id=None,  # Broadcast to all in society
        sender_id=sender_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # 2. Collect FCM tokens of all active members in society
    all_members = db.query(User).filter(
        User.society_id == society_id,
        User.is_active == True
    ).all()

    members_with_tokens = [m for m in all_members if m.fcm_token and m.fcm_token.strip()]
    tokens = [m.fcm_token.strip() for m in members_with_tokens]

    print("=" * 60)
    print(f"[BROADCAST DISPATCH]")
    print(f"Society ID: {society_id}")
    print(f"Sender ID: {sender_id}")
    print(f"Recipient users found in society: {len(all_members)}")
    print(f"Valid FCM tokens: {len(tokens)}")
    print(f"Title: {title}")
    print("=" * 60)
    logger.info(f"Broadcasting notification '{title}' to {len(tokens)} devices in society {society_id}")

    if tokens:
        payload_data = data.copy() if data else {}
        payload_data.update({
            "notification_id": str(notif.id),
            "notification_type": notification_type,
            "society_id": str(society_id)
        })
        send_fcm_multicast(
            tokens=tokens,
            title=title,
            body=message,
            data=payload_data,
            db=db
        )
    else:
        print("[BROADCAST WARNING] No active members with FCM tokens found in society. No push sent.")

    return notif



def get_user_unread_count(db: Session, user: User) -> int:
    """
    Computes the total number of unread notifications and messages for the user.
    Counts all notification types appearing in the user's Messages & Notifications view.
    """
    soc_id = user.society_id
    query = db.query(Notification)

    if soc_id:
        query = query.filter(
            (Notification.user_id == user.id) |
            ((Notification.society_id == soc_id) & (Notification.user_id.is_(None)))
        )
    else:
        query = query.filter(Notification.user_id == user.id)

    all_notifs = query.all()
    if not all_notifs:
        return 0

    # Get set of notification IDs that this user has marked as read
    read_ids = set(
        r[0] for r in db.query(NotificationRead.notification_id)
        .filter(NotificationRead.user_id == user.id)
        .all()
    )

    unread_count = 0
    for notif in all_notifs:
        # If notification has a record in notification_reads for this user, it's read
        if notif.id in read_ids:
            continue
        # If targeted directly to this user and flagged is_read, it's read
        if notif.user_id == user.id and notif.is_read:
            continue

        unread_count += 1

    return unread_count


def mark_notification_as_read(db: Session, user_id: int, notification_id: int) -> bool:
    """
    Marks a single notification as read for the user.
    """
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        return False

    # Check if already marked in NotificationRead
    existing_read = db.query(NotificationRead).filter(
        NotificationRead.notification_id == notification_id,
        NotificationRead.user_id == user_id
    ).first()

    if not existing_read:
        read_entry = NotificationRead(
            notification_id=notification_id,
            user_id=user_id
        )
        db.add(read_entry)

    # If targeted to this user, also update is_read
    if notif.user_id == user_id:
        notif.is_read = True

    db.commit()
    return True


def mark_all_notifications_as_read(db: Session, user: User) -> int:
    """
    Marks all notifications visible in the user's Messages & Notifications view as read.
    """
    soc_id = user.society_id
    query = db.query(Notification)

    if soc_id:
        query = query.filter(
            (Notification.user_id == user.id) |
            ((Notification.society_id == soc_id) & (Notification.user_id.is_(None)))
        )
    else:
        query = query.filter(Notification.user_id == user.id)


    all_notifs = query.all()
    if not all_notifs:
        return 0

    read_ids = set(
        r[0] for r in db.query(NotificationRead.notification_id)
        .filter(NotificationRead.user_id == user.id)
        .all()
    )

    marked_count = 0
    for notif in all_notifs:
        if notif.id not in read_ids:
            read_entry = NotificationRead(
                notification_id=notif.id,
                user_id=user.id
            )
            db.add(read_entry)
            marked_count += 1

        if notif.user_id == user.id:
            notif.is_read = True

    db.commit()
    return marked_count


