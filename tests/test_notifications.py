import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.models.user import User
from app.models.notification import Notification, NotificationRead
from app.services.notification_service import (
    send_user_notification,
    notify_society_chairman,
    broadcast_society_notification,
    send_fcm_multicast
)
from app.core.security import create_access_token

Base.metadata.create_all(bind=engine)

client = TestClient(app)

def get_test_token(mobile_number: str, user_type: int = 1) -> tuple[str, int]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile_number == mobile_number).first()
        if user:
            token = create_access_token(
                subject=user.id,
                role="resident" if user.user_type == 1 else "admin",
                society_id=user.society_id,
                user_type=user.user_type
            )
            return token, user.id
        token = create_access_token(
            subject=f"temp_{mobile_number}",
            role="admin" if user_type == 3 else "resident",
            society_id=None,
            user_type=user_type
        )
        return token, 0
    finally:
        db.close()

def test_update_fcm_token_and_notifications_api():
    # 1. Login as resident (no fcm_token in login call — token comes from device only)
    token, user_id = get_test_token("9800000001", user_type=1)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update FCM token via the dedicated endpoint (simulating what Flutter does)
    # Use a realistic-length placeholder (100+ chars) to satisfy the token length guard.
    # Real tokens from FirebaseMessaging.instance.getToken() are 140-200+ chars.
    test_fcm_token = "fcm_test_token_" + "a" * 100  # 115 chars total
    update_res = client.post("/api/user/update-fcm-token", json={"fcm_token": test_fcm_token}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["status"] == 1

    # Verify in DB, then immediately clear the test token so it doesn't pollute FCM tests
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        assert user.fcm_token == test_fcm_token
        # ⬇️ Always clean up test/fake tokens after assertion — never leave in DB
        user.fcm_token = None
        db.commit()
    finally:
        db.close()

    # 3. Fetch notifications
    notif_res = client.get("/api/notifications", headers=headers)
    assert notif_res.status_code == 200
    assert notif_res.json()["status"] == 1
    assert isinstance(notif_res.json()["data"], list)

    # 4. Fetch unread count
    unread_res = client.get("/api/notifications/unread-count", headers=headers)
    assert unread_res.status_code == 200
    assert unread_res.json()["status"] == 1
    assert "unread_count" in unread_res.json()["data"]

    # 5. Mark notifications read
    mark_res = client.post("/api/notifications/mark-read", json={"all": True}, headers=headers)
    assert mark_res.status_code == 200
    assert mark_res.json()["status"] == 1
    assert mark_res.json()["data"]["unread_count"] == 0




def test_chairman_broadcast_message():
    # 1. Login as Chairman
    token, _ = get_test_token("9800000000", user_type=3)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Broadcast announcement
    broadcast_res = client.post(
        "/api/chairman/broadcast-message",
        json={
            "title": "Water Tank Cleaning Notice",
            "message": "Water supply will be paused from 2 PM to 4 PM tomorrow.",
            "type": "WATER_ALERT"
        },
        headers=headers
    )
    assert broadcast_res.status_code == 200
    assert broadcast_res.json()["status"] == 1
    assert "id" in broadcast_res.json()["data"]


def test_notification_service_functions():
    db = SessionLocal()
    try:
        # Find test chairman and resident
        chairman = db.query(User).filter(User.user_type == 3, User.society_id.isnot(None)).first()
        resident = db.query(User).filter(User.user_type == 1, User.society_id.isnot(None)).first()
        assert chairman is not None
        assert resident is not None

        # Test single user notification
        notif = send_user_notification(
            db=db,
            user_id=resident.id,
            title="Unit Test Notification",
            message="This is a test message",
            notification_type="GENERAL"
        )
        assert notif is not None
        assert notif.user_id == resident.id
        assert notif.title == "Unit Test Notification"

        # Test chairman notification
        c_notifs = notify_society_chairman(
            db=db,
            society_id=chairman.society_id,
            title="Chairman Alert",
            message="New action required",
            notification_type="READING_REQUEST"
        )
        assert len(c_notifs) >= 1

        # Test multicast function with mock / fallback
        res = send_fcm_multicast(
            tokens=["dummy_token_1", "dummy_token_2"],
            title="Multicast Test",
            body="Multicast Body",
            db=db
        )
        assert "success_count" in res
        assert "failure_count" in res
    finally:
        db.close()


def test_fcm_test_push_api():
    token, _ = get_test_token("9800000001", user_type=1)
    headers = {"Authorization": f"Bearer {token}"}

    push_res = client.post(
        "/api/notifications/test-push",
        json={"title": "FCM Test", "body": "Testing push notification"},
        headers=headers
    )
    assert push_res.status_code == 200
    assert "data" in push_res.json()

