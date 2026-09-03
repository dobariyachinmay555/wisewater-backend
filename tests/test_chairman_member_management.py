import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.society import Society, Block, Flat
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill, Payment
from app.models.audit import AuditLog
from app.models.flat_occupancy import FlatOccupancyHistory
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
def setup_scenario(db):
    import random
    suf = random.randint(1000, 9999)
    society = Society(
        name=f"Member Test Soc {suf}",
        code=f"SOC-MM-{suf}",
        address="101 Test Road",
        city="Ahmedabad",
        state="Gujarat",
        zip_code="380015",
        status="ACTIVE",
        chairman_name="Chairman Boss",
        chairman_mobile=f"981110{suf}"
    )
    db.add(society)
    db.flush()

    block = Block(society_id=society.id, title="Block A", total_flats=10)
    db.add(block)
    db.flush()

    # Chairman
    chair = User(
        name="Chairman Boss",
        mobile_number=f"981110{suf}",
        email="chair@test.com",
        user_type=3,
        society_id=society.id,
        block_id=block.id,
        flat_number="A-101",
        approval_status=1,
        is_active=True,
        fcm_token=f"fcm_chair_{suf}"
    )
    db.add(chair)

    # Resident (Rahul)
    rahul = User(
        name="Rahul Sharma",
        mobile_number=f"982220{suf}",
        email="rahul@test.com",
        user_type=1,
        society_id=society.id,
        block_id=block.id,
        flat_number="A-102",
        approval_status=1,
        previous_unit=250,
        is_active=True,
        fcm_token=f"fcm_rahul_{suf}"
    )
    db.add(rahul)
    db.flush()

    # Physical Meter in Flat A-102
    meter = Meter(
        society_id=society.id,
        block_id=block.id,
        user_id=rahul.id,
        flat_number="A-102",
        meter_serial_number=f"MET-102-{suf}",
        initial_reading=100,
        current_reading=250,
        status="ACTIVE"
    )
    db.add(meter)
    db.flush()

    # Historical Readings for Rahul
    r1 = MeterReading(
        society_id=society.id,
        user_id=rahul.id,
        meter_id=meter.id,
        block_id=block.id,
        previous_unit=100,
        current_unit=180,
        total_unit=80,
        unit_price=25.0,
        total_price=2000.0,
        status=1
    )
    r2 = MeterReading(
        society_id=society.id,
        user_id=rahul.id,
        meter_id=meter.id,
        block_id=block.id,
        previous_unit=180,
        current_unit=250,
        total_unit=70,
        unit_price=25.0,
        total_price=1750.0,
        status=1
    )
    db.add_all([r1, r2])
    db.flush()

    # Historical Bills for Rahul
    b1 = Bill(
        bill_number=f"BILL-{suf}-01",
        society_id=society.id,
        user_id=rahul.id,
        reading_id=r1.id,
        billing_month=1,
        billing_year=2026,
        consumption_units=80,
        unit_price=25.0,
        total_amount=2000.0,
        payment_status="PAID"
    )
    b2 = Bill(
        bill_number=f"BILL-{suf}-02",
        society_id=society.id,
        user_id=rahul.id,
        reading_id=r2.id,
        billing_month=2,
        billing_year=2026,
        consumption_units=70,
        unit_price=25.0,
        total_amount=1750.0,
        payment_status="PENDING"
    )
    db.add_all([b1, b2])

    # Another Society & User (for cross-society isolation checks)
    other_soc = Society(
        name=f"Other Soc {suf}",
        code=f"SOC-OTH-{suf}",
        address="300 Other St",
        city="Ahmedabad",
        state="Gujarat",
        zip_code="380015",
        status="ACTIVE"
    )
    db.add(other_soc)
    db.flush()

    other_user = User(
        name="Other Resident",
        mobile_number=f"983330{suf}",
        email="other@test.com",
        user_type=1,
        society_id=other_soc.id,
        flat_number="B-101",
        is_active=True
    )
    db.add(other_user)
    db.commit()

    chair_token = create_access_token(subject=chair.id, role="admin", society_id=society.id, user_type=3)
    rahul_token = create_access_token(subject=rahul.id, role="resident", society_id=society.id, user_type=1)

    return {
        "society": society,
        "block": block,
        "chair": chair,
        "rahul": rahul,
        "meter": meter,
        "r1": r1,
        "r2": r2,
        "b1": b1,
        "b2": b2,
        "other_soc": other_soc,
        "other_user": other_user,
        "chair_token": chair_token,
        "rahul_token": rahul_token,
        "suffix": str(suf)
    }

def test_chairman_can_list_members_of_own_society(setup_scenario):
    data = setup_scenario
    res = client.get(
        "/api/chairman/members",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["status"] == 1
    members = json_data["data"]
    user_ids = [m["user_id"] for m in members]
    assert data["chair"].id in user_ids
    assert data["rahul"].id in user_ids
    # Other society user must NOT be included
    assert data["other_user"].id not in user_ids

def test_chairman_cannot_view_members_of_another_society(setup_scenario):
    data = setup_scenario
    # Attempting to fetch details of a member in another society
    res = client.get(
        f"/api/chairman/members/{data['other_user'].id}",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res.status_code == 404

def test_chairman_can_search_and_filter_members(setup_scenario):
    data = setup_scenario
    # Search by name
    res = client.get(
        "/api/chairman/members?search=Rahul",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res.status_code == 200
    members = res.json()["data"]
    assert len(members) == 1
    assert members[0]["name"] == "Rahul Sharma"

    # Search by flat
    res_flat = client.get(
        "/api/chairman/members?search=A-102",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res_flat.status_code == 200
    assert len(res_flat.json()["data"]) == 1

def test_resident_cannot_access_chairman_member_apis(setup_scenario):
    data = setup_scenario
    res = client.get(
        "/api/chairman/members",
        headers={"Authorization": f"Bearer {data['rahul_token']}"}
    )
    assert res.status_code == 403

def test_chairman_can_edit_member_profile(setup_scenario, db):
    data = setup_scenario
    rahul_id = data["rahul"].id
    res = client.put(
        f"/api/chairman/members/{rahul_id}",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "name": "Rahul S. Updated",
            "email": "rahul.new@test.com"
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == 1
    
    db.expire_all()
    updated_user = db.query(User).filter_by(id=rahul_id).first()
    assert updated_user.name == "Rahul S. Updated"
    assert updated_user.email == "rahul.new@test.com"

def test_cannot_change_mobile_to_already_registered_number(setup_scenario):
    data = setup_scenario
    # Attempt to change Rahul's mobile to Chairman's mobile (collision)
    res = client.put(
        f"/api/chairman/members/{data['rahul'].id}",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={"mobile_number": data["chair"].mobile_number}
    )
    assert res.status_code == 200
    assert res.json()["status"] == 0
    assert "already registered" in res.json()["message"]

def test_replace_member_preserves_old_readings_and_bills(setup_scenario, db):
    data = setup_scenario
    rahul = data["rahul"]
    rahul_id = rahul.id
    new_mob = f"998880{data['suffix']}"

    with patch("app.services.notification_service.send_user_notification") as mock_notif:
        res = client.post(
            f"/api/chairman/members/{rahul_id}/replace",
            headers={"Authorization": f"Bearer {data['chair_token']}"},
            json={
                "new_name": "Amit Patel",
                "new_mobile_number": new_mob,
                "new_email": "amit@test.com",
                "reason": "Tenant change"
            }
        )
        assert res.status_code == 200
        assert res.json()["status"] == 1

        db.expire_all()

        # 1. Verify Rahul's historical readings still belong to Rahul
        readings = db.query(MeterReading).filter(MeterReading.user_id == rahul_id).all()
        assert len(readings) == 2
        for r in readings:
            assert r.user_id == rahul_id  # NEVER REASSIGNED TO AMIT!

        # 2. Verify Rahul's historical bills still belong to Rahul
        bills = db.query(Bill).filter(Bill.user_id == rahul_id).all()
        assert len(bills) == 2
        for b in bills:
            assert b.user_id == rahul_id  # NEVER REASSIGNED TO AMIT!

        # Verify Rahul is now inactive and no longer assigned to Flat A-102
        rahul_after = db.query(User).filter_by(id=rahul_id).first()
        assert rahul_after.is_active is False
        assert rahul_after.flat_number is None

        # 3. Verify Amit is the new active member for Flat A-102
        amit = db.query(User).filter(User.mobile_number == new_mob).first()
        assert amit is not None
        assert amit.name == "Amit Patel"
        assert amit.flat_number == "A-102"
        assert amit.is_active is True
        # Consumption baseline starts at meter current_reading (250)
        assert amit.previous_unit == 250

        # 4. Verify Meter now points to Amit but current_reading is 250
        meter = db.query(Meter).filter_by(id=data["meter"].id).first()
        assert meter.user_id == amit.id
        assert meter.current_reading == 250

        # 5. Verify FlatOccupancyHistory record
        occ = db.query(FlatOccupancyHistory).filter(FlatOccupancyHistory.user_id == amit.id).first()
        assert occ is not None
        assert occ.flat_number == "A-102"
        assert occ.start_meter_reading == 250
        assert occ.is_current is True

        # 6. Verify Outgoing Occupancy History closed for Rahul
        rahul_occ = db.query(FlatOccupancyHistory).filter(FlatOccupancyHistory.user_id == rahul_id).first()
        if rahul_occ:
            assert rahul_occ.is_current is False
            assert rahul_occ.end_meter_reading == 250

        # 7. Verify Audit Log recorded
        audit = db.query(AuditLog).filter(AuditLog.action == "MEMBER_REPLACED").first()
        assert audit is not None
        assert audit.society_id == data["society"].id

def test_replace_member_rejects_other_society_user(setup_scenario):
    data = setup_scenario
    res = client.post(
        f"/api/chairman/members/{data['rahul'].id}/replace",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "new_name": "Infiltrator",
            "new_mobile_number": data["other_user"].mobile_number,
            "reason": "Move between societies"
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == 0
    assert "another society" in res.json()["message"]

def test_change_flat_validates_target_occupancy(setup_scenario):
    data = setup_scenario
    # Attempting to move Rahul to Chairman's flat (A-101) which is occupied
    res = client.put(
        f"/api/chairman/members/{data['rahul'].id}/change-flat",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "target_block_id": data["block"].id,
            "target_flat_number": "A-101"
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == 0
    assert "already occupied" in res.json()["message"]

def test_change_flat_success(setup_scenario, db):
    data = setup_scenario
    # Moving Rahul to vacant flat A-105
    res = client.put(
        f"/api/chairman/members/{data['rahul'].id}/change-flat",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "target_block_id": data["block"].id,
            "target_flat_number": "A-105"
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == 1

    db.expire_all()
    updated = db.query(User).filter_by(id=data["rahul"].id).first()
    assert updated.flat_number == "A-105"

def test_old_member_can_still_access_historical_records_after_replacement(setup_scenario, db):
    data = setup_scenario
    rahul = data["rahul"]
    rahul_token = data["rahul_token"]

    # Replace Rahul with brand new resident
    new_mob = f"995550{data['suffix']}"
    rep_res = client.post(
        f"/api/chairman/members/{rahul.id}/replace",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "new_name": "New Flat Resident",
            "new_mobile_number": new_mob,
            "reason": "Rahul moved out"
        }
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["status"] == 1

    # Rahul should still be able to query readings API for his historical bills/readings!
    readings_res = client.get(
        "/api/get-unit-readings",
        headers={"Authorization": f"Bearer {rahul_token}"}
    )
    assert readings_res.status_code == 200
    history = readings_res.json()["data"]
    # Rahul still has access to his 2 historical readings
    assert len(history) == 2

    # Rahul should still be able to download his historical bill PDF!
    bill_res = client.get(
        f"/api/download-bill-pdf/{data['r1'].id}",
        headers={"Authorization": f"Bearer {rahul_token}"}
    )
    assert bill_res.status_code == 200
    assert bill_res.json()["status"] == 1
    assert "file_url" in bill_res.json()["data"]

def test_chairman_cannot_change_member_role_to_chairman(setup_scenario):
    data = setup_scenario
    # Attempting to edit member and inject user_type = 3
    res = client.put(
        f"/api/chairman/members/{data['rahul'].id}",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={"user_type": 3, "name": "Fake Chairman"}
    )
    assert res.status_code == 200
    # user_type must not be modified by this endpoint
    assert res.json()["data"].get("user_type") != 3

def test_replace_member_reuses_same_society_resident(setup_scenario, db):
    data = setup_scenario
    soc_id = data["society"].id
    suf = data["suffix"]
    
    # Create another resident in the same society
    existing_res = User(
        name="Sunil Existing",
        mobile_number=f"996660{suf}",
        email="sunil@test.com",
        user_type=1,
        society_id=soc_id,
        flat_number="A-108",
        approval_status=1,
        is_active=True
    )
    db.add(existing_res)
    db.commit()

    # Replace Rahul with Sunil
    res = client.post(
        f"/api/chairman/members/{data['rahul'].id}/replace",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "new_name": "Sunil Existing",
            "new_mobile_number": existing_res.mobile_number,
            "reason": "Internal flat shift"
        }
    )
    assert res.status_code == 200
    assert res.json()["status"] == 1

    db.expire_all()
    # Verify no duplicate account was created
    matches = db.query(User).filter(User.mobile_number == existing_res.mobile_number).all()
    assert len(matches) == 1
    assert matches[0].id == existing_res.id
    assert matches[0].flat_number == "A-102"

def test_get_member_details_endpoint(setup_scenario):
    data = setup_scenario
    res = client.get(
        f"/api/chairman/members/{data['rahul'].id}",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res.status_code == 200
    d = res.json()["data"]
    assert d["user_id"] == data["rahul"].id
    assert d["name"] == data["rahul"].name
    assert d["meter_number"] == data["meter"].meter_serial_number
    assert "occupancy_history" in d

def test_invalid_member_id_returns_404(setup_scenario):
    data = setup_scenario
    res = client.get(
        "/api/chairman/members/999999",
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert res.status_code == 404

def test_replace_member_sends_targeted_notifications_only(setup_scenario):
    data = setup_scenario
    rahul = data["rahul"]
    new_mob = f"994440{data['suffix']}"

    with patch("app.services.notification_service.send_user_notification") as mock_user_notif, \
         patch("app.services.notification_service.broadcast_society_notification") as mock_broad:

        res = client.post(
            f"/api/chairman/members/{rahul.id}/replace",
            headers={"Authorization": f"Bearer {data['chair_token']}"},
            json={
                "new_name": "Private Replacement",
                "new_mobile_number": new_mob,
                "reason": "Private change"
            }
        )
        assert res.status_code == 200
        # Broadcast MUST NOT be called!
        assert not mock_broad.called
        # Targeted user notification MUST be called!
        assert mock_user_notif.called

def test_replace_resident_seamless_reading_history_and_future_consumption(setup_scenario, db):
    data = setup_scenario
    rahul = data["rahul"]
    rahul_id = rahul.id
    soc_id = data["society"].id
    block_id = data["block"].id
    meter = data["meter"]

    # At start: meter current_reading is 250, Rahul has 2 readings (r1: 180, r2: 250)
    assert meter.current_reading == 250
    assert rahul.previous_unit == 250

    new_mob = f"997770{data['suffix']}"

    # Chairman replaces Rahul with Amit Patel
    replace_res = client.post(
        f"/api/chairman/members/{rahul_id}/replace",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={
            "new_name": "Amit Patel",
            "new_mobile_number": new_mob,
            "new_email": "amit.patel@test.com",
            "reason": "Change of tenancy"
        }
    )
    assert replace_res.status_code == 200
    assert replace_res.json()["status"] == 1

    db.expire_all()

    # 1. Old Resident Verification:
    # Inactive, flat cleared, historical records safe
    rahul_after = db.query(User).filter_by(id=rahul_id).first()
    assert rahul_after.is_active is False
    assert rahul_after.flat_number is None

    # Verify Rahul does NOT appear in active member list for the society
    active_members_res = client.get(
        "/api/apartment-block/users",
        params={"block_id": block_id},
        headers={"Authorization": f"Bearer {data['chair_token']}"}
    )
    assert active_members_res.status_code == 200
    member_names = [m["name"] for m in active_members_res.json().get("data", [])]
    assert rahul.name not in member_names
    assert "Amit Patel" in member_names

    # 2. New Resident Verification:
    # Active resident of same society, block, and flat
    amit = db.query(User).filter(User.mobile_number == new_mob).first()
    assert amit is not None
    assert amit.is_active is True
    assert amit.society_id == soc_id
    assert amit.block_id == block_id
    assert amit.flat_number == "A-102"
    # Starting/previous reading MUST be meter's current reading (250)
    assert amit.previous_unit == 250

    # 3. Meter Continuity:
    # Same physical meter, current reading NOT reset (remains 250), linked to Amit
    meter_after = db.query(Meter).filter_by(id=meter.id).first()
    assert meter_after.user_id == amit.id
    assert meter_after.current_reading == 250
    assert meter_after.flat_number == "A-102"

    # 4. Seamless Reading History for New Resident:
    # Amit logs in and calls get-unit-readings
    amit_token = create_access_token(
        subject=amit.id,
        role="resident",
        society_id=soc_id,
        user_type=1
    )
    amit_readings_res = client.get(
        "/api/get-unit-readings",
        headers={"Authorization": f"Bearer {amit_token}"}
    )
    assert amit_readings_res.status_code == 200
    flat_readings = amit_readings_res.json()["data"]
    # Amit can seamlessly see the 2 historical readings of Flat A-102 (250 and 180)
    assert len(flat_readings) == 2
    assert flat_readings[0]["current_unit"] == 250
    assert flat_readings[1]["current_unit"] == 180

    # 5. Future Reading under New Resident:
    # Amit submits reading of 280 units
    submit_res = client.post(
        "/api/store-unit-reading",
        headers={"Authorization": f"Bearer {amit_token}"},
        data={"unit": "280"}
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == 1
    new_reading_id = submit_res.json()["data"]["user_unit_history_id"]

    # Verify consumption calculation: 280 - 250 = 30 units!
    db.expire_all()
    new_reading = db.query(MeterReading).filter_by(id=new_reading_id).first()
    assert new_reading.user_id == amit.id  # Belongs to Amit!
    assert new_reading.previous_unit == 250
    assert new_reading.current_unit == 280
    assert new_reading.total_unit == 30
    assert new_reading.total_price == 30 * 25.0  # 750.0

    # 6. Chairman Approves Amit's Reading:
    approve_res = client.post(
        "/api/pending-unit-reading-requests/update-status",
        headers={"Authorization": f"Bearer {data['chair_token']}"},
        json={"user_unit_history_id": new_reading_id, "status": 1}
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == 1

    # Verify Amit's previous_unit advances to 280 and Meter advances to 280
    db.expire_all()
    amit_after_read = db.query(User).filter_by(id=amit.id).first()
    meter_final = db.query(Meter).filter_by(id=meter.id).first()
    assert amit_after_read.previous_unit == 280
    assert meter_final.current_reading == 280

    # 7. Old Resident Historical Immutability:
    # Rahul's historical readings still have user_id == Rahul.id and were never changed!
    rahul_readings = db.query(MeterReading).filter(MeterReading.user_id == rahul_id).all()
    assert len(rahul_readings) == 2
    for rr in rahul_readings:
        assert rr.user_id == rahul_id

