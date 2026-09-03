import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.society import Society, Block
from app.models.user import User
from app.models.chairman_transfer import ChairmanTransfer
from app.models.audit import AuditLog
from app.core.security import create_access_token

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
        is_active=True
    )
    db.add(res_user)

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

def test_successful_transfer_flow_promoting_resident(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]
    res_mobile = data["res_user"].mobile_number

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent")

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
        init_data = init_res.json()
        assert init_data["status"] == 1
        transfer_id = init_data["data"]["transfer_id"]

        transfer = db.query(ChairmanTransfer).filter_by(id=transfer_id).first()
        assert transfer is not None
        assert transfer.status == "PENDING_OTP"
        assert not transfer.is_verified
        otp_code = transfer.otp_code

        v_res = client.post(
            "/api/chairman/transfer/verify-otp",
            json={
                "transfer_id": transfer_id,
                "mobile_number": res_mobile,
                "otp_code": otp_code
            }
        )
        assert v_res.status_code == 200
        assert v_res.json()["status"] == 1
        assert v_res.json()["data"]["status"] == "OTP_VERIFIED"

        comp_res = client.post(
            "/api/chairman/transfer/complete",
            headers={"Authorization": f"Bearer {chair_token}"},
            json={"transfer_id": transfer_id, "demote_old_to_resident": True}
        )
        assert comp_res.status_code == 200
        assert comp_res.json()["status"] == 1

        db.expire_all()
        old_chair = db.query(User).filter_by(id=data["chair_user"].id).first()
        assert old_chair.user_type == 1
        assert old_chair.flat_number == "A-101"
        assert old_chair.previous_unit == 150

        new_chair = db.query(User).filter_by(mobile_number=res_mobile).first()
        assert new_chair.id == data["res_user"].id
        assert new_chair.user_type == 3
        assert new_chair.name == "New Promoted Chairman"

        soc = db.query(Society).filter_by(id=data["society"].id).first()
        assert soc.chairman_name == "New Promoted Chairman"
        assert soc.chairman_mobile == res_mobile

        audit = db.query(AuditLog).filter_by(action="CHAIRMAN_TRANSFERRED", entity_id=str(soc.id)).first()
        assert audit is not None

        # Old chairman immediately loses permissions
        denied_res = client.get(
            "/api/chairman/transfer/status",
            headers={"Authorization": f"Bearer {chair_token}"}
        )
        assert denied_res.status_code == 403

def test_verify_and_complete_endpoint(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]
    brand_new_mobile = f"997200{data['suffix']}"

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent")

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

        new_u = db.query(User).filter_by(mobile_number=brand_new_mobile).first()
        assert new_u is not None
        assert new_u.user_type == 3
        assert new_u.society_id == data["society"].id

def test_cancel_pending_transfer(setup_transfer_scenario, db):
    data = setup_transfer_scenario
    chair_token = data["chair_token"]

    with patch("app.api.v1.mobile.chairman.send_sms_otp", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (True, "OTP sent")

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
        assert cancel_res.json()["status"] == 1

        transfer = db.query(ChairmanTransfer).filter_by(id=transfer_id).first()
        assert transfer.status == "CANCELLED"
