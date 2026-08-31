import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.society import Society, Block, Flat
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.seed_society_50 import seed_society_50_members

from app.core.security import create_access_token

client = TestClient(app)

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

@pytest.fixture(scope="module", autouse=True)
def setup_society_and_50_members():
    """Ensure database has the 50-member society seeded before running tests."""
    db = SessionLocal()
    try:
        seed_society_50_members(db=db)
    finally:
        db.close()

def test_society_and_blocks_structure():
    """Verify Society and Blocks exist in DB and API."""
    db = SessionLocal()
    try:
        society = db.query(Society).filter(Society.code == "SOC-GP50").first()
        assert society is not None
        assert society.name == "Green Palms Residency"
        assert society.status == "ACTIVE"
        assert len(society.blocks) == 2
        
        # Verify 50 flats
        total_flats = db.query(Flat).filter(Flat.society_id == society.id).count()
        assert total_flats == 50
    finally:
        db.close()

def test_resolve_society_by_code():
    """Test resolving society structure by SOC-GP50 code for invite/joining."""
    res = client.get("/api/society/by-code/SOC-GP50")
    assert res.status_code == 200
    assert res.json()["status"] == 1
    data = res.json()["data"]
    assert data["name"] == "Green Palms Residency"
    assert data["total_flats"] == 50
    assert len(data["blocks"]) == 2
    assert len(data["blocks"][0]["flats"]) == 25
    assert len(data["blocks"][1]["flats"]) == 25

def test_chairman_login_and_dashboard():
    """Test Chairman login and dashboard metrics with 50 members."""
    token = get_test_token("9800000000", user_type=3)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get Dashboard Summary
    dash_res = client.get("/api/chairman/dashboard-summary", headers=headers)
    assert dash_res.status_code == 200
    assert dash_res.json()["status"] == 1
    dash_data = dash_res.json()["data"]
    
    assert dash_data["society_name"] == "Green Palms Residency"
    assert dash_data["total_units"] == 50
    assert dash_data["total_blocks"] == 2
    assert dash_data["joined_members"] >= 50
    assert dash_data["total_meters"] >= 50
    assert len(dash_data["blocks"]) == 2

    # 3. Get Society Profile
    profile_res = client.get("/api/chairman/society", headers=headers)
    assert profile_res.status_code == 200
    assert profile_res.json()["status"] == 1
    assert profile_res.json()["data"]["name"] == "Green Palms Residency"

    # 4. Get Flats List
    flats_res = client.get("/api/chairman/society/flats", headers=headers)
    assert flats_res.status_code == 200
    assert flats_res.json()["status"] == 1
    assert len(flats_res.json()["data"]) == 50

def test_fetch_all_50_members():
    """Test retrieving all 50 members through apartment-block/users API."""
    # Login as Chairman
    token = get_test_token("9800000000", user_type=3)
    headers = {"Authorization": f"Bearer {token}"}

    # Get all users for the society
    users_res = client.get("/api/apartment-block/users", headers=headers)
    assert users_res.status_code == 200
    assert users_res.json()["status"] == 1
    members = users_res.json()["data"]
    
    # Check that at least 50 members are returned
    assert len(members) >= 50
    
    # Check that member phone numbers and flats are properly formatted
    tower_a_flats = [m["flat_number"] for m in members if m["flat_number"].startswith("A-")]
    tower_b_flats = [m["flat_number"] for m in members if m["flat_number"].startswith("B-")]
    assert len(tower_a_flats) >= 25
    assert len(tower_b_flats) >= 25

def test_individual_members_login_and_profile():
    """Test sample members logging in and accessing their profiles."""
    test_members = [
        ("9800000000", "A-101", 3),
        ("9800000002", "A-102", 1),
        ("9800000025", "A-505", 1),
        ("9800000026", "B-101", 1),
        ("9800000050", "B-505", 1),
    ]

    for mobile, expected_flat, role in test_members:
        token = get_test_token(mobile, user_type=role)
        # Get profile
        prof_res = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
        assert prof_res.status_code == 200
        assert prof_res.json()["status"] == 1
        assert prof_res.json()["data"]["flat_number"] == expected_flat

def test_50_pending_reading_requests_one_per_member():
    """Verify all 50 members have exactly 1 pending reading request."""
    # Login as Chairman
    c_token = get_test_token("9800000000", user_type=3)
    c_headers = {"Authorization": f"Bearer {c_token}"}

    # Fetch pending reading requests
    res = client.get("/api/pending-unit-reading-requests", headers=c_headers)
    assert res.status_code == 200
    assert res.json()["status"] == 1
    items = res.json()["data"]

    assert len(items) == 50, f"Expected 50 pending reading requests, got {len(items)}"
    
    # Ensure every member ID appears exactly once (1 request per member)
    user_ids = [item["user_details"]["user_id"] for item in items if item.get("user_details")]
    assert len(user_ids) == 50
    assert len(set(user_ids)) == 50, "Every member must have exactly 1 pending request"

def test_meter_readings_and_pending_approvals():
    """Test reading submission by member and approval by Chairman."""
    # 1. Login as Member 2
    m_token = get_test_token("9800000002", user_type=1)
    m_headers = {"Authorization": f"Bearer {m_token}"}

    # Member submits new reading dynamically > previous_unit
    prof = client.get("/api/profile", headers=m_headers).json()["data"]
    prev_u = int(prof.get("previous_unit") or 100)
    sub_res = client.post(
        "/api/store-unit-reading",
        data={"unit": str(prev_u + 50)},
        headers=m_headers
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == 1

    # 2. Login as Chairman and view pending reading requests
    c_token = get_test_token("9800000000", user_type=3)
    c_headers = {"Authorization": f"Bearer {c_token}"}

    pending_res = client.get("/api/pending-unit-reading-requests", headers=c_headers)
    assert pending_res.status_code == 200
    assert pending_res.json()["status"] == 1
    pending_items = pending_res.json()["data"]
    assert len(pending_items) >= 1

    # Approve the reading
    reading_id = pending_items[0]["user_unit_history_id"]
    approve_res = client.post(
        "/api/pending-unit-reading-requests/update-status",
        json={"user_unit_history_id": reading_id, "status": 1},
        headers=c_headers
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == 1

def test_chairman_edit_society_profile_and_photo_frequency():
    """Test Chairman editing society profile and setting photo submission rule (1 vs 6 Months)."""
    # 1. Login as Chairman
    c_token = get_test_token("9800000000", user_type=3)
    c_headers = {"Authorization": f"Bearer {c_token}"}

    # 2. Get Society Profile & check default photo frequency
    get_res = client.get("/api/chairman/society", headers=c_headers)
    assert get_res.status_code == 200
    assert get_res.json()["status"] == 1
    assert "photo_submission_frequency" in get_res.json()["data"]

    # 3. Update photo submission frequency to 6 Months
    update_res = client.put(
        "/api/chairman/society",
        json={
            "address": "Plot 101, Updated Silicon Boulevard, Satellite Road",
            "unit_price": 28.50,
            "photo_submission_frequency": "6_MONTHS",
            "contact_number": "07926850099"
        },
        headers=c_headers
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == 1
    assert update_res.json()["data"]["photo_submission_frequency"] == "6_MONTHS"

    # 4. Verify updated setting in GET profile
    verify_get = client.get("/api/chairman/society", headers=c_headers)
    assert verify_get.status_code == 200
    assert verify_get.json()["data"]["photo_submission_frequency"] == "6_MONTHS"
    assert verify_get.json()["data"]["unit_price"] == 28.50

    # 5. Switch back to 1 Month
    switch_res = client.put(
        "/api/chairman/society",
        json={"photo_submission_frequency": "1_MONTH", "unit_price": 25.00},
        headers=c_headers
    )
    assert switch_res.status_code == 200
    assert switch_res.json()["data"]["photo_submission_frequency"] == "1_MONTH"

def test_download_reports_one_month_and_six_months():
    """Test downloading 1-Month and 6-Months water consumption reports."""
    # Login as Chairman
    c_token = get_test_token("9800000000", user_type=3)
    c_headers = {"Authorization": f"Bearer {c_token}"}

    # 1. Download 1-Month Report
    rep_1m = client.get(
        "/api/download-reading-history-report?period_type=1_MONTH&start_date=2026-08-01&end_date=2026-08-31",
        headers=c_headers
    )
    assert rep_1m.status_code == 200
    assert rep_1m.json()["status"] == 1
    data_1m = rep_1m.json()["data"]
    assert "reading_report_" in data_1m["file_url"]
    assert data_1m["total_members"] >= 50
    assert data_1m["total_consumption"] >= 0
    assert data_1m["total_revenue"] >= 0

    # 2. Download 6-Months (Bi-Annual) Report
    rep_6m = client.get(
        "/api/download-reading-history-report?period_type=6_MONTHS&start_date=2026-01-01&end_date=2026-06-30",
        headers=c_headers
    )
    assert rep_6m.status_code == 200
    assert rep_6m.json()["status"] == 1
    data_6m = rep_6m.json()["data"]
    assert "reading_report_" in data_6m["file_url"]
    assert data_6m["total_members"] >= 50
    assert data_6m["period_type"] == "6_MONTHS"

def test_cmp_super_admin_views_50_member_society():
    """Test CMP Admin viewing the society and all member statistics."""
    # Login as Super Admin
    cmp_login = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    assert cmp_login.status_code == 200
    cmp_token = cmp_login.json()["access_token"]
    cmp_headers = {"Authorization": f"Bearer {cmp_token}"}

    # List Societies with search
    soc_res = client.get("/api/v1/cmp/societies?search=GP50", headers=cmp_headers)
    assert soc_res.status_code == 200
    items = soc_res.json()["items"]
    gp_soc = next((s for s in items if s["code"] == "SOC-GP50"), None)
    assert gp_soc is not None
    assert gp_soc["name"] == "Green Palms Residency"
    assert gp_soc["total_flats"] == 50
    assert gp_soc["status"] == "ACTIVE"

def test_download_individual_bill_pdf():
    """Test generating and downloading individual resident water bill PDF invoice."""
    # 1. Login as Chairman & get pending readings
    c_token = get_test_token("9800000000", user_type=3)
    c_headers = {"Authorization": f"Bearer {c_token}"}

    pending_res = client.get("/api/pending-unit-reading-requests", headers=c_headers)
    assert pending_res.status_code == 200
    pending_items = pending_res.json()["data"]
    assert len(pending_items) > 0
    first_reading_id = pending_items[0]["user_unit_history_id"]

    # 2. Approve the reading
    client.post(
        "/api/pending-unit-reading-requests/update-status",
        json={"user_unit_history_id": first_reading_id, "status": 1},
        headers=c_headers
    )

    # 3. Download Bill PDF
    pdf_res = client.get(f"/api/download-bill-pdf/{first_reading_id}", headers=c_headers)
    assert pdf_res.status_code == 200
    assert pdf_res.json()["status"] == 1
    pdf_data = pdf_res.json()["data"]
    assert "WaterBill_" in pdf_data["file_url"]
    assert pdf_data["file_url"].endswith(".pdf")




