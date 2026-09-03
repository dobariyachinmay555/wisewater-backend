import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.society import Society, Block
from app.models.user import User
from app.models.chairman_transfer import ChairmanTransfer
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.core.security import create_access_token
from app.services.notification_service import get_user_unread_count

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def setup_transfer_scenario(db):
    import random
    code_suf = random.randint(1000, 9999)
    society = Society(
        name=f"Transfer Test Society {code_suf}",
        code=f"SOC-TR-{code_suf}",
        address="100 Test St",
        city="Ahmedabad",
        state="Gujarat",
        zip_code="380015",
        unit_price=25.0,
        status="ACTIVE",
        chairman_name="Initial Chairman",
        chairman_mobile=f"981110{code_suf}",
        chairman_email="init.chair@test.com"
    )
    db.add(society)
    db.flush()

    block = Block(society_id=society.id, title="Block A", total_flats=10)
    db.add(block)
    db.flush()

    chair_user = User(
        name="Initial Chairman",
        mobile_number=f"981110{code_suf}",
        email="init.chair@test.com",
        user_type=3,
        society_id=society.id,
        block_id=block.id,
        flat_number="A-101",
        approval_status=1,
        previous_unit=150,
        fcm_token=f"fcm_token_chair_{code_suf}",
        is_active=True
    )
    db.add(chair_user)

    res_user = User(
        name="Existing Resident",
        mobile_number=f"982220{code_suf}",
        email="res@test.com",
        user_type=1,
        society_id=society.id,
        block_id=block.id,
        flat_number="A-102",
        approval_status=1,
        previous_unit=80,
        fcm_token=f"fcm_token_resident_{code_suf}",
        is_active=True
    )
    db.add(res_user)

    # Resident WITHOUT FCM token (must be skipped safely)
    res_no_token = User(
        name="No Token Resident",
        mobile_number=f"984440{code_suf}",
        email="notoken@test.com",
        user_type=1,
        society_id=society.id,
        block_id=block.id,
        flat_number="A-103",
        approval_status=1,
        previous_unit=50,
        fcm_token=None,
        is_active=True
    )
    db.add(res_no_token)

    other_soc = Society(
        name=f"Other Society {code_suf}",
        code=f"SOC-OT-{code_suf}",
        address="200 Other St",
        city="Ahmedabad",
        state="Gujarat",
        zip_code="380015",
        status="ACTIVE",
        chairman_name="Other Chair",
        chairman_mobile=f"983330{code_suf}"
    )
    db.add(other_soc)
    db.flush()

    other_chair = User(
        name="Other Chair",
        mobile_number=f"983330{code_suf}",
        user_type=3,
        society_id=other_soc.id,
        approval_status=1,
        fcm_token=f"fcm_token_other_soc_{code_suf}",
        is_active=True
    )
    db.add(other_chair)
    db.commit()

    chair_token = create_access_token(subject=chair_user.id, role="admin", society_id=society.id, user_type=3)
    res_token = create_access_token(subject=res_user.id, role="resident", society_id=society.id, user_type=1)

    return {
        "society": society,
        "chair_user": chair_user,
        "res_user": res_user,
        "res_no_token": res_no_token,
        "other_soc": other_soc,
        "other_chair": other_chair,
        "chair_token": chair_token,
        "res_token": res_token,
        "suffix": str(code_suf)
    }

def test_resident_cannot_initiate_transfer(setup_transfer_scenario):
    data = setup_transfer_scenario
    res = client.post(
        "/api/chairman/transfer/initiate",
        headers={"Authorization": f"Bearer {data['res_token']}"},
        json={"new_mobile_number": "9990001111", "new_name": "Hacked Chair"}
    )
    assert res.status_code == 403

def test_cannot_transfer_to_self(setup_transfer_scenario):
    data = setup_transfer_scenario
    res = client.post(
        "/api/chairman/transfer/initiate",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={"new_mobile_number": data["chair_user"].mobile_number, "new_name": "Self"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == 0
    assert "own current mobile" in res.json()["message"]

def test_cannot_transfer_to_other_society_chairman(setup_transfer_scenario):
    data = setup_transfer_scenario
    res = client.post(
        "/api/chairman/transfer/initiate",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={"new_mobile_number": data["other_chair"].mobile_number, "new_name": "Other"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == 0
    assert "already registered as Chairman" in res.json()["message"]

def test_successful_transfer_flow_promoting_resident_with_broadcast_notification(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]
    res_mobile = data["res_user"].mobile_number
    soc_id = data["society"].id

    initial_unread = get_user_unread_count(db, data["res_user"])

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_sms, \
         patch("app.services.notification_service.send_fcm_multicast") as mock_fcm:

        mock_sms.return_value = (True, "OTP sent")
        mock_fcm.return_value = {"success_count": 2, "failure_count": 0, "invalid_tokens": []}

        init_res = client.post(
            "/api/chairman/transfer/initiate",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={
                "new_mobile_number": res_mobile,
                "new_name": "New Promoted Chairman",
                "new_email": "promoted@test.com"
            }
        )
        assert init_res.status_code == 200
        transfer_id = init_res.json()["data"]["transfer_id"]
        transfer = db.query(ChairmanTransfer).filter_by(id=transfer_id).first()

        v_res = client.post(
            "/api/chairman/transfer/verify-otp",
            json={
                "transfer_id": transfer_id,
                "mobile_number": res_mobile,
                "otp_code": transfer.otp_code
            }
        )
        assert v_res.status_code == 200

        # Complete transfer
        comp_res = client.post(
            "/api/chairman/transfer/complete",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={"transfer_id": transfer_id, "demote_old_to_resident": True}
        )
        assert comp_res.status_code == 200
        assert comp_res.json()["status"] == 1

        db.expire_all()
        # Verify FCM notification was triggered
        assert mock_fcm.called
        call_kwargs = mock_fcm.call_args[1]
        targeted_tokens = call_kwargs["tokens"]

        # Eligible members with tokens in this society MUST be targeted
        assert data["chair_user"].fcm_token in targeted_tokens
        assert data["res_user"].fcm_token in targeted_tokens

        # Members of ANOTHER society must NOT be targeted
        assert data["other_chair"].fcm_token not in targeted_tokens

        # Exact title and message requirements
        assert call_kwargs["title"] == "Chairman Changed"
        assert f"The Chairman of {data['society'].name} has been changed to New Promoted Chairman." in call_kwargs["body"]

        # In-app notification record was stored
        notif = db.query(Notification).filter_by(
            society_id=soc_id,
            title="Chairman Changed"
        ).first()
        assert notif is not None
        assert notif.user_id is None  # Society-wide broadcast

        # Unread count increases for society residents
        new_unread = get_user_unread_count(db, data["res_user"])
        assert new_unread == initial_unread + 1

def test_failed_or_cancelled_transfer_does_not_send_notification(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_sms, \
         patch("app.services.notification_service.send_fcm_multicast") as mock_fcm:

        mock_sms.return_value = (True, "OTP sent")

        init_res = client.post(
            "/api/chairman/transfer/initiate",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={
                "new_mobile_number": "9912345678",
                "new_name": "Cancelled Candidate"
            }
        )
        transfer_id = init_res.json()["data"]["transfer_id"]

        cancel_res = client.post(
            "/api/chairman/transfer/cancel",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={"transfer_id": transfer_id, "reason": "Mistake"}
        )
        assert cancel_res.status_code == 200

        # No FCM notification must be sent
        assert not mock_fcm.called

        # No notification record created for the cancelled candidate
        notif = db.query(Notification).filter(
            Notification.society_id == data["society"].id,
            Notification.message.contains("Cancelled Candidate")
        ).first()
        assert notif is None

def test_verify_and_complete_endpoint_sends_notification(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]
    brand_new_mobile = f"997200{data['suffix']}"

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_sms, \
         patch("app.services.notification_service.send_fcm_multicast") as mock_fcm:

        mock_sms.return_value = (True, "OTP sent")
        mock_fcm.return_value = {"success_count": 2, "failure_count": 0, "invalid_tokens": []}

        init_res = client.post(
            "/api/chairman/transfer/initiate",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={
                "new_mobile_number": brand_new_mobile,
                "new_name": "Brand New Candidate"
            }
        )
        transfer_id = init_res.json()["data"]["transfer_id"]
        transfer = db.query(ChairmanTransfer).filter_by(id=transfer_id).first()

        comb_res = client.post(
            "/api/chairman/transfer/verify-and-complete",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={
                "transfer_id": transfer_id,
                "mobile_number": brand_new_mobile,
                "otp_code": transfer.otp_code,
                "demote_old_to_resident": True
            }
        )
        assert comb_res.status_code == 200
        assert comb_res.json()["status"] == 1

        # Broadcast notification verified
        assert mock_fcm.called
        call_kwargs = mock_fcm.call_args[1]
        assert call_kwargs["title"] == "Chairman Changed"
        assert f"Brand New Candidate" in call_kwargs["body"]
