import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

from unittest.mock import patch, AsyncMock
from app.core.database import SessionLocal
from app.models.otp import OtpVerification
from app.core.security import create_access_token
from app.models.user import User

def get_test_token(mobile_number: str, user_type: int = 1) -> str:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile_number == mobile_number).first()
        if user:
            return create_access_token(
                subject=user.id,
                role="resident" if user.user_type == 1 else "admin",
                society_id=user.society_id,
                user_type=user.user_type
            )
        return create_access_token(
            subject=f"temp_{mobile_number}",
            role="admin" if user_type == 3 else "resident",
            society_id=None,
            user_type=user_type
        )
    finally:
        db.close()

def test_mobile_send_and_verify_otp():
    db = SessionLocal()
    try:
        with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (True, "OTP sent successfully")
            # 1. Send OTP
            send_res = client.post("/api/send-otp", json={"mobile_number": "9999988888", "device_type": "1"})
            assert send_res.status_code == 200
            assert send_res.json()["status"] == 1
            assert "otp" not in send_res.json().get("data", {})
            
            otp_entry = db.query(OtpVerification).filter_by(mobile_number="9999988888").first()
            assert otp_entry is not None
            otp = otp_entry.otp_code
            
            # 2. Verify OTP
            verify_res = client.post("/api/verify-otp", json={"mobile_number": "9999988888", "otp": otp, "user_type": 3})
            assert verify_res.status_code == 200
            assert verify_res.json()["status"] == 1
            data = verify_res.json()["data"]
            assert "token" in data
            assert data["user_details"]["mobile_number"] == "9999988888"
            assert data["user_details"]["user_type"] == 3  # Chairman
    finally:
        db.close()

def test_mobile_profile_and_societies():
    # Login to get valid token
    token = get_test_token("9800000000", user_type=3)
    headers = {"Authorization": f"Bearer {token}"}

    # Get profile
    profile_res = client.get("/api/profile", headers=headers)
    assert profile_res.status_code == 200
    assert profile_res.json()["status"] == 1
    assert "user_id" in profile_res.json()["data"]
    
    # Update profile (Name & Email)
    update_res = client.post("/api/profile/update", json={"name": "Rajesh Sharma", "email": "rajesh@example.com"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["status"] == 1
    assert update_res.json()["data"]["name"] == "Rajesh Sharma"
    
    # Search societies
    soc_res = client.get("/api/search-apartments")
    assert soc_res.status_code == 200
    assert soc_res.json()["status"] == 1
    
    # Apartment blocks
    blocks_res = client.get("/api/apartment-blocks", headers=headers)
    assert blocks_res.status_code == 200
    assert blocks_res.json()["status"] == 1

def test_mobile_readings_and_billing():
    token = get_test_token("9800000001", user_type=1)
    headers = {"Authorization": f"Bearer {token}"}

    readings_res = client.get("/api/get-unit-readings", headers=headers)
    assert readings_res.status_code == 200
    assert readings_res.json()["status"] == 1

def test_cmp_login_and_dashboard_metrics():
    # 1. Invalid login
    bad_login = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "wrongpassword"})
    assert bad_login.status_code == 401
    
    # 2. Valid Super Admin login
    login_res = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token is not None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Dashboard Metrics
    metrics_res = client.get("/api/v1/cmp/dashboard/metrics", headers=headers)
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert "total_societies" in metrics
    assert "monthly_platform_revenue" in metrics

def test_cmp_societies_and_audit():
    login_res = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # List societies
    soc_list = client.get("/api/v1/cmp/societies", headers=headers)
    assert soc_list.status_code == 200
    assert "items" in soc_list.json()
    
    # Check audit logs
    audit_res = client.get("/api/v1/cmp/audit-logs", headers=headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()["items"]
    assert len(logs) >= 1
