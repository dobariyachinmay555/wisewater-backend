import pytest
import uuid
import random
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models.society import Society, Block, Flat
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.models.audit import AuditLog
from app.models.notification import Notification

client = TestClient(app)

def make_mobile():
    return f'9{random.randint(100000000, 999999999)}'

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def cmp_admin_token():
    res = client.post('/api/v1/cmp/auth/login', json={'email': 'admin@wisewater.com', 'password': 'admin123'})
    assert res.status_code == 200, f'CMP Login failed: {res.text}'
    return res.json()['access_token']

@pytest.fixture
def cmp_headers(cmp_admin_token):
    return {'Authorization': f'Bearer {cmp_admin_token}'}

@pytest.fixture
def setup_audit_test_society(db: Session):
    unique_suffix = uuid.uuid4().hex[:6]
    soc_code = f'SOC-AUD-{unique_suffix}'

    soc = Society(
        name=f'CMP Audit Palms {unique_suffix}',
        code=soc_code,
        property_category='FLAT_APARTMENT',
        address='100 Ring Road',
        city='Ahmedabad',
        state='Gujarat',
        zip_code='380015',
        unit_price=25.0,
        status='ACTIVE'
    )
    db.add(soc)
    db.commit()
    db.refresh(soc)

    block = Block(society_id=soc.id, title='Tower Z', total_flats=10)
    db.add(block)
    db.commit()
    db.refresh(block)

    chair = User(
        name='Sunil Chairman',
        mobile_number=make_mobile(),
        email=f'sunil.{unique_suffix}@audit.com',
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-101',
        user_type=3,
        approval_status=1,
        is_active=True
    )
    db.add(chair)

    sec = User(
        name='Vikas Secretary',
        mobile_number=make_mobile(),
        email=f'vikas.{unique_suffix}@audit.com',
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-102',
        user_type=2,
        approval_status=1,
        is_active=True
    )
    db.add(sec)

    rahul = User(
        name='Rahul Tenant',
        mobile_number=make_mobile(),
        email=f'rahul.{unique_suffix}@audit.com',
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-103',
        user_type=1,
        approval_status=1,
        is_active=True,
        previous_unit=250.0,
        fcm_token='rahul_fcm_token_test'
    )
    db.add(rahul)

    priya = User(
        name='Priya Resident',
        mobile_number=make_mobile(),
        email=f'priya.{unique_suffix}@audit.com',
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-104',
        user_type=1,
        approval_status=1,
        is_active=True,
        previous_unit=180.0,
        fcm_token='priya_fcm_token_test'
    )
    db.add(priya)
    db.commit()

    meter_z103 = Meter(
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-103',
        user_id=rahul.id,
        meter_serial_number=f'MTR-Z103-{unique_suffix}',
        current_reading=250.0
    )
    meter_z104 = Meter(
        society_id=soc.id,
        block_id=block.id,
        flat_number='Z-104',
        user_id=priya.id,
        meter_serial_number=f'MTR-Z104-{unique_suffix}',
        current_reading=180.0
    )
    db.add_all([meter_z103, meter_z104])
    db.commit()

    hist_reading = MeterReading(
        user_id=rahul.id,
        society_id=soc.id,
        meter_id=meter_z103.id,
        previous_unit=200.0,
        current_unit=250.0,
        total_unit=50.0,
        unit_price=25.0,
        total_price=1250.0,
        status=1
    )
    db.add(hist_reading)
    db.commit()

    hist_bill = Bill(
        user_id=rahul.id,
        society_id=soc.id,
        bill_number=f'BILL-AUDIT-Z103-{unique_suffix}',
        billing_month=9,
        billing_year=2026,
        consumption_units=50,
        unit_price=25.0,
        total_amount=1250.0,
        payment_status='PAID'
    )
    db.add(hist_bill)
    db.commit()

    yield {
        'society': soc,
        'block': block,
        'chairman': chair,
        'secretary': sec,
        'rahul': rahul,
        'priya': priya,
        'meter_z103': meter_z103,
        'meter_z104': meter_z104,
        'hist_reading': hist_reading,
        'hist_bill': hist_bill,
        'suffix': unique_suffix
    }

    db.query(AuditLog).filter(AuditLog.society_id == soc.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id.in_([rahul.id, priya.id, chair.id, sec.id])).delete(synchronize_session=False)
    db.query(Bill).filter(Bill.society_id == soc.id).delete(synchronize_session=False)
    db.query(MeterReading).filter(MeterReading.society_id == soc.id).delete(synchronize_session=False)
    db.query(Meter).filter(Meter.society_id == soc.id).delete(synchronize_session=False)
    db.query(User).filter(User.society_id == soc.id).delete(synchronize_session=False)
    db.query(Block).filter(Block.society_id == soc.id).delete(synchronize_session=False)
    db.delete(soc)
    db.commit()

def test_chairman_replaces_resident_audit_trail(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    chair = data['chairman']
    rahul = data['rahul']
    soc = data['society']
    suf = data['suffix']

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    payload = {
        'new_name': 'Amit Shah',
        'new_mobile_number': make_mobile(),
        'new_email': f'amit.{suf}@audit.com',
        'reason': 'Rahul moved out, lease expired',
        'deactivate_old_member': True
    }

    res = client.post(f'/api/chairman/members/{rahul.id}/replace', json=payload, headers=chair_headers)
    assert res.status_code == 200, f'Replace failed: {res.text}'
    res_data = res.json()
    assert res_data['status'] == 1

    audit_entry = db.query(AuditLog).filter(
        AuditLog.society_id == soc.id,
        AuditLog.action == 'MEMBER_REPLACED'
    ).order_by(AuditLog.created_at.desc()).first()

    assert audit_entry is not None
    assert audit_entry.actor_id == str(chair.id)
    assert audit_entry.action == 'MEMBER_REPLACED'
    assert audit_entry.entity_type == 'FLAT'

    after = audit_entry.after_state
    assert after['action'] == 'MEMBER_REPLACED'
    assert after['flat_number'] == 'Z-103'
    assert after['meter_reading'] == 250.0
    assert after['new_starting_reading'] == 250.0
    assert after['reason'] == 'Rahul moved out, lease expired'
    assert after['performed_by_name'] == 'Sunil Chairman'
    assert after['performed_by_role'] == 'Chairman'
    assert after['old_member']['name'] == 'Rahul Tenant'
    assert after['new_member']['name'] == 'Amit Shah'
    assert 'Rahul Tenant' in after['change_summary'] and 'Amit Shah' in after['change_summary']

    cmp_res = client.get(f'/api/v1/cmp/audit-logs?society_id={soc.id}&action=MEMBER_REPLACED', headers=cmp_headers)
    assert cmp_res.status_code == 200
    cmp_items = cmp_res.json()['items']
    assert len(cmp_items) >= 1

    item = cmp_items[0]
    assert item['action'] == 'MEMBER_REPLACED'
    assert 'Rahul Tenant' in item['change_summary'] and 'Amit Shah' in item['change_summary']
    assert item['old_member_name'] == 'Rahul Tenant'
    assert item['new_member_name'] == 'Amit Shah'
    assert item['flat_number'] == 'Z-103'
    assert item['meter_reading'] == 250.0
    assert item['performed_by_name'] == 'Sunil Chairman'
    assert item['performed_by_role'] == 'Chairman'

def test_chairman_removes_resident_audit_trail(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    chair = data['chairman']
    priya = data['priya']
    soc = data['society']

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    payload = {'reason': 'Flat vacated and kept vacant'}
    res = client.post(f'/api/chairman/members/{priya.id}/remove', json=payload, headers=chair_headers)
    assert res.status_code == 200
    assert res.json()['status'] == 1

    audit_entry = db.query(AuditLog).filter(
        AuditLog.society_id == soc.id,
        AuditLog.action == 'MEMBER_REMOVED'
    ).order_by(AuditLog.created_at.desc()).first()

    assert audit_entry is not None
    assert audit_entry.actor_id == str(chair.id)
    after = audit_entry.after_state
    assert after['action'] == 'MEMBER_REMOVED'
    assert after['old_member']['name'] == 'Priya Resident'
    assert after['new_member']['name'] == 'VACANT'
    assert after['meter_reading'] == 180.0
    assert 'Priya Resident' in after['change_summary'] and 'VACANT' in after['change_summary']

    cmp_res = client.get(f'/api/v1/cmp/audit-logs?society_id={soc.id}&action=MEMBER_REMOVED', headers=cmp_headers)
    assert cmp_res.status_code == 200
    items = cmp_res.json()['items']
    assert len(items) >= 1
    assert 'Priya Resident' in items[0]['change_summary'] and 'VACANT' in items[0]['change_summary']
    assert items[0]['new_member_name'] == 'VACANT'
    assert items[0]['meter_reading'] == 180.0

def test_society_member_history_endpoint(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    soc = data['society']
    chair = data['chairman']
    priya = data['priya']

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    client.post(f'/api/chairman/members/{priya.id}/remove', json={'reason': 'Moved abroad'}, headers=chair_headers)

    res = client.get(f'/api/v1/cmp/societies/{soc.id}/member-history', headers=cmp_headers)
    assert res.status_code == 200
    history = res.json()['items']
    assert len(history) >= 1

    h = history[0]
    assert h['action'] == 'MEMBER_REMOVED'
    assert h['old_member_name'] == 'Priya Resident'
    assert h['new_member_name'] == 'VACANT'
    assert h['flat_number'] == 'Z-104'
    assert h['meter_reading'] == 180.0

def test_cmp_audit_search_and_filters(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    soc = data['society']
    chair = data['chairman']
    rahul = data['rahul']
    new_mob = make_mobile()

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    replace_res = client.post(f'/api/chairman/members/{rahul.id}/replace', json={
        'new_name': 'Karan Johar',
        'new_mobile_number': new_mob,
        'reason': 'New family moved in'
    }, headers=chair_headers)
    assert replace_res.status_code == 200
    assert replace_res.json()['status'] == 1

    res_name = client.get('/api/v1/cmp/audit-logs?search=Karan', headers=cmp_headers)
    assert res_name.status_code == 200
    assert any('Karan' in item.get('change_summary', '') for item in res_name.json()['items'])

    res_mob = client.get(f'/api/v1/cmp/audit-logs?search={new_mob}', headers=cmp_headers)
    assert res_mob.status_code == 200
    assert len(res_mob.json()['items']) >= 1

    res_flat = client.get('/api/v1/cmp/audit-logs?search=Z-103', headers=cmp_headers)
    assert res_flat.status_code == 200
    assert len(res_flat.json()['items']) >= 1

def test_cmp_users_reflects_current_relationship(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    soc = data['society']
    chair = data['chairman']
    rahul = data['rahul']

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    replace_res = client.post(f'/api/chairman/members/{rahul.id}/replace', json={
        'new_name': 'Deepak Verma',
        'new_mobile_number': make_mobile(),
        'reason': 'Tenant replacement'
    }, headers=chair_headers)
    assert replace_res.status_code == 200
    assert replace_res.json()['status'] == 1

    res_rahul = client.get(f'/api/v1/cmp/users?search={rahul.mobile_number}', headers=cmp_headers)
    assert res_rahul.status_code == 200
    items = res_rahul.json()['items']
    assert len(items) >= 1
    rahul_item = items[0]
    assert rahul_item['is_unassigned'] is True
    assert rahul_item['society_name'] == 'Unassigned'
    assert rahul_item['flat_number'] == 'N/A'
    assert rahul_item['is_active'] is False

    res_unassigned = client.get('/api/v1/cmp/users?unassigned_only=true', headers=cmp_headers)
    assert res_unassigned.status_code == 200
    unassigned_ids = [u['id'] for u in res_unassigned.json()['items']]
    assert rahul.id in unassigned_ids

def test_failed_member_action_does_not_create_audit_event(db: Session, setup_audit_test_society, cmp_headers):
    data = setup_audit_test_society
    soc = data['society']
    chair = data['chairman']

    chair_token = create_access_token(subject=chair.id, role='admin', society_id=soc.id, user_type=3)
    chair_headers = {'Authorization': f'Bearer {chair_token}'}

    initial_count = db.query(AuditLog).filter(AuditLog.society_id == soc.id).count()

    bad_res = client.post('/api/chairman/members/999999/replace', json={
        'new_name': 'Ghost',
        'new_mobile_number': '9999999999'
    }, headers=chair_headers)
    assert bad_res.status_code in [404, 400, 403, 422]

    after_count = db.query(AuditLog).filter(AuditLog.society_id == soc.id).count()
    assert after_count == initial_count, 'Failed replacement must not commit an audit log'

def test_audit_logs_are_immutable_and_cannot_be_deleted(cmp_headers):
    del_res = client.delete('/api/v1/cmp/audit-logs', headers=cmp_headers)
    assert del_res.status_code in [404, 405], 'Audit logs must not be deletable'

    patch_res = client.patch('/api/v1/cmp/audit-logs/1', headers=cmp_headers)
    assert patch_res.status_code in [404, 405], 'Audit logs must not be modifiable'
