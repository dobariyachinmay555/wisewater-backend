import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.otp import OtpVerification
from app.models.user import User
from app.services.sms_service import generate_otp, normalize_indian_mobile, send_sms_otp
from app.core.config import settings

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 1 & 2. OTP generation & 6 digits length
def test_otp_generation_length_and_format():
    for _ in range(50):
        otp = generate_otp(6)
        assert len(otp) == 6
        assert otp.isdigit()
        assert int(otp) >= 100000
        assert int(otp) <= 999999

# 3. OTP is not predictable or hard-coded
def test_otp_not_hardcoded_and_random():
    otps = {generate_otp(6) for _ in range(100)}
    # Generating 100 6-digit numbers should produce at least 95 unique values
    assert len(otps) >= 95
    assert "1234" not in otps
    assert "123456" not in otps

# 4. OTP expires after 10 minutes
def test_otp_expiry_duration(db_session):
    mobile = "9988776655"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        res = client.post("/api/send-otp", json={"mobile_number": mobile})
        assert res.status_code == 200
        assert res.json()["status"] == 1
        
        otp_entry = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first()
        assert otp_entry is not None
        
        # Check expiry is ~10 minutes from created_at
        now = datetime.now(timezone.utc)
        exp = otp_entry.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        
        diff = (exp - now).total_seconds()
        assert 540 <= diff <= 610  # roughly 9 to 10.1 minutes

# 5. Correct OTP succeeds
def test_correct_otp_succeeds(db_session):
    mobile = "9876500010"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        client.post("/api/send-otp", json={"mobile_number": mobile})
        
        otp_entry = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first()
        assert otp_entry is not None
        actual_otp = otp_entry.otp_code
        
        verify_res = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": actual_otp})
        assert verify_res.status_code == 200
        assert verify_res.json()["status"] == 1
        assert "token" in verify_res.json()["data"]

# 6. Incorrect OTP fails
def test_incorrect_otp_fails(db_session):
    mobile = "9876500011"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        client.post("/api/send-otp", json={"mobile_number": mobile})
        
        verify_res = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "000000"})
        assert verify_res.status_code == 200
        assert verify_res.json()["status"] == 0
        assert "Invalid OTP" in verify_res.json()["message"]

# 7. 5 failed attempts invalidate OTP
def test_five_failed_attempts_lockout(db_session):
    mobile = "9876500012"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        client.post("/api/send-otp", json={"mobile_number": mobile})
        
        otp_entry = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first()
        actual_otp = otp_entry.otp_code
        
        # 4 incorrect attempts
        for i in range(1, 5):
            res = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "999999"})
            assert res.json()["status"] == 0
            assert f"{5 - i} attempt" in res.json()["message"]
            
        # 5th incorrect attempt -> exceeds maximum attempts
        res5 = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "999999"})
        assert res5.json()["status"] == 0
        assert "Maximum verification attempts exceeded" in res5.json()["message"]
        
        # Even correct OTP is now rejected because max attempts was reached
        res_after = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": actual_otp})
        assert res_after.json()["status"] == 0
        assert "Maximum verification attempts exceeded" in res_after.json()["message"]

# 8. Expired OTP fails
def test_expired_otp_fails(db_session):
    mobile = "9876500013"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        client.post("/api/send-otp", json={"mobile_number": mobile})
        
        otp_entry = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first()
        actual_otp = otp_entry.otp_code
        
        # Force expiration into past
        otp_entry.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()
        
        verify_res = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": actual_otp})
        assert verify_res.status_code == 200
        assert verify_res.json()["status"] == 0
        assert "expired" in verify_res.json()["message"].lower()

# 9. Used OTP cannot be reused
def test_used_otp_cannot_be_reused(db_session):
    mobile = "9876500014"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        client.post("/api/send-otp", json={"mobile_number": mobile})
        
        otp_entry = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first()
        actual_otp = otp_entry.otp_code
        
        # 1st verification succeeds
        v1 = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": actual_otp})
        assert v1.json()["status"] == 1
        
        # 2nd verification with same OTP is rejected
        v2 = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": actual_otp})
        assert v2.json()["status"] == 0
        assert "already been used" in v2.json()["message"].lower()

# 10. New OTP invalidates old OTP
def test_new_otp_invalidates_old_otp(db_session):
    mobile = "9876500015"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        
        # 1st Send
        client.post("/api/send-otp", json={"mobile_number": mobile})
        otp1 = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first().otp_code
        
        # 2nd Send
        client.post("/api/send-otp", json={"mobile_number": mobile})
        otp2 = db_session.query(OtpVerification).filter_by(mobile_number=mobile).first().otp_code
        
        assert otp1 != otp2
        
        # Old OTP fails
        v_old = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": otp1})
        assert v_old.json()["status"] == 0
        
        # New OTP succeeds
        v_new = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": otp2})
        assert v_new.json()["status"] == 1

# 11. /send-otp does not return OTP in response
def test_send_otp_does_not_leak_otp():
    mobile = "9876500016"
    with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent successfully")
        res = client.post("/api/send-otp", json={"mobile_number": mobile})
        data = res.json()
        assert data["status"] == 1
        assert "otp" not in data.get("data", {})
        assert "debug_otp" not in data.get("data", {})

# 12. /send-otp reports failure when SMS provider fails in production mode
def test_send_otp_reports_gateway_failure():
    mobile = "9876500017"
    with patch.object(settings, "ENABLE_TEST_OTP_BYPASS", False):
        with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (False, "Unable to send OTP via SMS. Please check your number or try again later.")
            res = client.post("/api/send-otp", json={"mobile_number": mobile})
            data = res.json()
            assert data["status"] == 0
            assert "Unable to send OTP" in data["message"]
            assert "otp" not in data.get("data", {})

# 13 & 14. 1234 and 123456 are blocked when ENABLE_TEST_OTP_BYPASS=False, and 1234 works when True
def test_static_bypasses_are_blocked_in_production(db_session):
    mobile = "9876500018"
    with patch.object(settings, "ENABLE_TEST_OTP_BYPASS", False):
        with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (True, "OTP sent successfully")
            client.post("/api/send-otp", json={"mobile_number": mobile})
            
            # Try 1234 (invalid length or wrong code)
            res_1234 = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "1234"})
            assert res_1234.json()["status"] == 0
            
            # Try 123456 (wrong code)
            res_123456 = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "123456"})
            assert res_123456.json()["status"] == 0

def test_test_bypass_works_when_enabled(db_session):
    mobile = "9876500019"
    with patch.object(settings, "ENABLE_TEST_OTP_BYPASS", True):
        with patch("app.api.v1.mobile.auth.send_sms_otp", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (False, "Gateway unavailable")
            send_res = client.post("/api/send-otp", json={"mobile_number": mobile})
            assert send_res.json()["status"] == 1
            
            verify_res = client.post("/api/verify-otp", json={"mobile_number": mobile, "otp": "1234", "user_type": 1})
            assert verify_res.status_code == 200
            assert verify_res.json()["status"] == 1
            assert "token" in verify_res.json()["data"]

# 15. Missing SMS API key does NOT produce fake success
@pytest.mark.asyncio
async def test_missing_fast2sms_api_key_fails():
    with patch.object(settings, "FAST2SMS_API_KEY", ""):
        with patch.object(settings, "SMS_PROVIDER", "fast2sms"):
            success, msg = await send_sms_otp("9876543210", "123456")
            assert success is False
            assert "not configured" in msg.lower()

def test_indian_mobile_normalization():
    assert normalize_indian_mobile("9876543210") == "9876543210"
    assert normalize_indian_mobile("+919876543210") == "9876543210"
    assert normalize_indian_mobile("919876543210") == "9876543210"
    assert normalize_indian_mobile("09876543210") == "9876543210"
    assert normalize_indian_mobile("+91 98765 43210") == "9876543210"
    assert normalize_indian_mobile("12345") is None
    assert normalize_indian_mobile("") is None
