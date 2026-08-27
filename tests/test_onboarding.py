import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_onboarding_otp_send_and_verify():
    # 1. Send OTP
    res = client.post("/api/onboarding/send-otp", json={"mobile_number": "9998887771"})
    assert res.status_code == 200
    assert res.json()["status"] == 1
    assert res.json()["data"]["otp"] == "1234"
    
    # 2. Verify OTP
    verify_res = client.post("/api/onboarding/verify-otp", json={"mobile_number": "9998887771", "otp": "1234"})
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == 1
    assert verify_res.json()["data"]["verified"] is True

def test_onboarding_register_flat_society_and_auto_flats():
    mobile = "9876500001"
    payload = {
        "society_name": "Skyline Heights Residency",
        "property_category": "FLAT_APARTMENT",
        "address": "456 Skyline Road, Satellite",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "pin_code": "380015",
        "blocks": [
            {"title": "Tower A", "total_flats": 10},
            {"title": "Tower B", "total_flats": 15}
        ],
        "chairman_name": "Vikram Patel",
        "chairman_mobile": mobile,
        "chairman_email": "vikram.patel@example.com"
    }
    
    reg_res = client.post("/api/onboarding/register", json=payload)
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == 1
    data = reg_res.json()["data"]
    assert "REG-" in data["registration_id"]
    assert data["registration_status"] == "PENDING"
    society_id = data["society_id"]
    token = data["token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check onboarding status
    status_res = client.get("/api/onboarding/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == 1
    s_data = status_res.json()["data"]
    assert s_data["total_blocks"] == 2
    assert s_data["total_flats"] == 25
    assert len(s_data["blocks"]) == 2

def test_onboarding_register_row_house_society():
    mobile = "9876500002"
    payload = {
        "society_name": "Royal Villas Community",
        "property_category": "ROW_HOUSE",
        "address": "789 Royal Enclave, Bopal",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "pin_code": "380058",
        "total_houses": 40,
        "chairman_name": "Aarav Sharma",
        "chairman_mobile": mobile,
        "chairman_email": "aarav.sharma@example.com"
    }
    
    reg_res = client.post("/api/onboarding/register", json=payload)
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == 1
    data = reg_res.json()["data"]
    assert data["property_category"] == "ROW_HOUSE"
    society_id = data["society_id"]
    token = data["token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check onboarding status
    status_res = client.get("/api/onboarding/status", headers=headers)
    assert status_res.status_code == 200
    s_data = status_res.json()["data"]
    assert s_data["total_houses"] == 40

def test_cmp_review_approve_society_registration():
    # 1. Login as CMP Super Admin
    cmp_login = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    assert cmp_login.status_code == 200
    cmp_token = cmp_login.json()["access_token"]
    cmp_headers = {"Authorization": f"Bearer {cmp_token}"}
    
    # 2. List registrations in CMP
    list_res = client.get("/api/v1/cmp/societies/registrations/all", headers=cmp_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) >= 1
    
    pending_soc = next((s for s in items if s["registration_status"] == "PENDING"), items[0])
    soc_id = pending_soc["id"]
    
    # 3. Approve Registration
    app_res = client.post(f"/api/v1/cmp/societies/registrations/{soc_id}/approve", headers=cmp_headers)
    assert app_res.status_code == 200
    assert app_res.json()["status"] == 1
    assert "SOC-" in app_res.json()["code"]

def test_cmp_request_changes_and_resubmit():
    # 1. Register a society
    mobile = "9876500003"
    payload = {
        "society_name": "Green Meadows",
        "property_category": "FLAT_APARTMENT",
        "address": "123 Old Address",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "pin_code": "380015",
        "blocks": [{"title": "Block A", "total_flats": 20}],
        "chairman_name": "Rohan Gupta",
        "chairman_mobile": mobile,
        "chairman_email": "rohan@example.com"
    }
    reg_res = client.post("/api/onboarding/register", json=payload)
    data = reg_res.json()["data"]
    soc_id = data["society_id"]
    token = data["token"]
    chairman_headers = {"Authorization": f"Bearer {token}"}
    
    # 2. CMP Admin requests changes
    cmp_login = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    cmp_headers = {"Authorization": f"Bearer {cmp_login.json()['access_token']}"}
    
    req_res = client.post(
        f"/api/v1/cmp/societies/registrations/{soc_id}/request-changes",
        json={"notes": "Please provide full updated street address with landmark"},
        headers=cmp_headers
    )
    assert req_res.status_code == 200
    
    # 3. Chairman checks status
    status_res = client.get("/api/onboarding/status", headers=chairman_headers)
    assert status_res.json()["data"]["registration_status"] == "CHANGES_REQUIRED"
    assert "landmark" in status_res.json()["data"]["change_request_notes"]
    
    # 4. Chairman resubmits
    resubmit_res = client.put(
        "/api/onboarding/resubmit",
        json={"address": "123 Updated Green Meadows Road, Near Iscon Temple"},
        headers=chairman_headers
    )
    assert resubmit_res.status_code == 200
    assert resubmit_res.json()["data"]["registration_status"] == "PENDING"

def test_chairman_add_member_and_code_resolution():
    # 1. Register a society and approve it
    mobile = "9898887088"
    payload = {
        "society_name": "Avlon Heights",
        "property_category": "FLAT_APARTMENT",
        "address": "nikol",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "pin_code": "382350",
        "blocks": [{"title": "Block A", "total_flats": 24}],
        "chairman_name": "chinmay",
        "chairman_mobile": mobile,
        "chairman_email": "chinmay@example.com"
    }
    reg_res = client.post("/api/onboarding/register", json=payload)
    soc_id = reg_res.json()["data"]["society_id"]
    token = reg_res.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # CMP Approves
    cmp_login = client.post("/api/v1/cmp/auth/login", json={"email": "admin@wisewater.com", "password": "admin123"})
    cmp_headers = {"Authorization": f"Bearer {cmp_login.json()['access_token']}"}
    appr_res = client.post(f"/api/v1/cmp/societies/registrations/{soc_id}/approve", headers=cmp_headers)
    assert appr_res.status_code == 200
    soc_code = appr_res.json().get("code")

    # 2. Chairman directly adds a member
    add_res = client.post(
        "/api/chairman/members/add",
        json={
            "name": "Kavita Shah",
            "mobile_number": "9123456789",
            "email": "kavita@example.com",
            "flat_number": "A-101",
            "role": 1
        },
        headers=headers
    )
    assert add_res.status_code == 200
    assert add_res.json()["status"] == 1
    assert add_res.json()["data"]["name"] == "Kavita Shah"
    assert add_res.json()["data"]["approval_status"] == 1

    # 3. Resolve society by code (for invite links)
    by_code_res = client.get(f"/api/society/by-code/{soc_code}")
    assert by_code_res.status_code == 200
    assert by_code_res.json()["status"] == 1
    assert by_code_res.json()["data"]["name"] == "Avlon Heights"
    assert len(by_code_res.json()["data"]["blocks"]) == 1

    # 4. Member submits join request
    join_token_res = client.post("/api/onboarding/verify-otp", json={"mobile_number": "9876543210", "otp": "1234"})
    member_token = join_token_res.json()["data"]["token"]
    join_res = client.post(
        "/api/society/join-request",
        json={
            "society_code": soc_code,
            "name": "Suresh Patel",
            "mobile_number": "9876543210",
            "flat_number": "A-102",
            "role": 1
        },
        headers={"Authorization": f"Bearer {member_token}"}
    )
    assert join_res.status_code == 200
    assert join_res.json()["status"] == 1
    assert join_res.json()["data"]["user_details"]["approval_status"] == 0  # Pending approval
