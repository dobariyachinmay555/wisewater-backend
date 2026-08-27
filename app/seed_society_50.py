import os
import random
from datetime import datetime, timezone, date, timedelta
from app.core.database import engine, Base, SessionLocal
from app.models.society import Society, Block, Flat
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.models.company import SubscriptionPlan

MEMBER_NAMES = [
    "Aarav Patel", "Diya Shah", "Rohan Mehta", "Priya Joshi", "Vikram Trivedi",
    "Ananya Sharma", "Aditya Verma", "Sneha Iyer", "Kunal Nair", "Pooja Deshmukh",
    "Siddharth Rao", "Kavita Singhal", "Rahul Gupta", "Neha Agarwal", "Varun Chopra",
    "Tanvi Kulkarni", "Harsh Vardhan", "Ishita Saxena", "Manish Pandey", "Ritu Bhatia",
    "Gaurav Kapoor", "Meera Pillai", "Nikhil Chawla", "Shreya Reddy", "Amit Malhotra",
    "Bhavna Dave", "Chirag Somani", "Deepak Bansal", "Ekta Mishra", "Farhan Khan",
    "Geeta Sundaram", "Himanshu Soni", "Indu Venkatesh", "Jayesh Parmar", "Kiran Hegde",
    "Lalit Rawat", "Monika Sen", "Naveen Nambiar", "Omkar Shinde", "Payal Jain",
    "Quasar Ali", "Radhika Menon", "Sameer Goswami", "Trisha Bhattacharya", "Umesh Tiwari",
    "Vandana Merchant", "Wasim Akram", "Xavier Dsouza", "Yashvi Parekh", "Zainab Merchant"
]

def seed_society_50_members(db=None):
    """Seed Green Palms Residency with 50 members, flats, meters, and readings."""
    should_close = False
    if db is None:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        should_close = True

    try:
        print("--- Seeding 1 Society with 50 Members ---")
        
        # 1. Get or assign subscription plan
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_type == "ANNUAL").first()
        plan_id = plan.id if plan else None

        # 2. Check / Create Society
        society = db.query(Society).filter(Society.code == "SOC-GP50").first()
        if not society:
            society = Society(
                name="Green Palms Residency",
                code="SOC-GP50",
                registration_id="REG-GP50-2026",
                property_category="FLAT_APARTMENT",
                address="Plot 101, Near Silicon Boulevard, Satellite Road",
                city="Ahmedabad",
                state="Gujarat",
                zip_code="380015",
                unit_price=25.00,
                status="ACTIVE",
                subscription_status="ACTIVE",
                subscription_plan_id=plan_id,
                subscription_start_date=datetime.now(timezone.utc) - timedelta(days=60),
                subscription_renewal_date=datetime.now(timezone.utc) + timedelta(days=305),
                chairman_name="Rajesh Sharma",
                chairman_mobile="9800000000",
                chairman_email="rajesh.sharma@wisewater.com",
                contact_number="07926850000",
                society_email="contact@greenpalms.org",
                establishment_year=2024,
                registration_status="ACTIVE"
            )
            db.add(society)
            db.flush()
            print(f"Created Society: {society.name} (ID: {society.id}, Code: {society.code})")

        soc_id = society.id

        # 3. Create Chairman Account
        chairman = db.query(User).filter(User.mobile_number == "9800000000").first()
        if not chairman:
            chairman = User(
                name="Rajesh Sharma",
                mobile_number="9800000000",
                email="rajesh.sharma@wisewater.com",
                user_type=3,  # Chairman
                society_id=soc_id,
                flat_number="A-101",
                approval_status=1,
                previous_unit=150,
                is_active=True
            )
            db.add(chairman)
            db.flush()

        # 4. Create 2 Blocks (Tower A: 25 flats, Tower B: 25 flats = Total 50 flats)
        block_a = db.query(Block).filter(Block.society_id == soc_id, Block.title == "Tower A").first()
        if not block_a:
            block_a = Block(society_id=soc_id, title="Tower A", total_flats=25)
            db.add(block_a)
            db.flush()

        block_b = db.query(Block).filter(Block.society_id == soc_id, Block.title == "Tower B").first()
        if not block_b:
            block_b = Block(society_id=soc_id, title="Tower B", total_flats=25)
            db.add(block_b)
            db.flush()

        if chairman.block_id != block_a.id:
            chairman.block_id = block_a.id
            db.flush()

        # 5. Create 50 Flats and 50 Members
        # 25 in Tower A (A-101 to A-505) and 25 in Tower B (B-101 to B-505)
        flats_config = []
        for floor in range(1, 6):
            for unit in range(1, 6):
                flats_config.append(("Tower A", block_a.id, f"A-{floor}0{unit}"))
        for floor in range(1, 6):
            for unit in range(1, 6):
                flats_config.append(("Tower B", block_b.id, f"B-{floor}0{unit}"))

        members_created = 0
        readings_created = 0
        bills_created = 0

        for idx, (block_title, blk_id, flat_no) in enumerate(flats_config):
            # 5a. Create / Update Flat
            flat = db.query(Flat).filter(
                Flat.society_id == soc_id,
                Flat.block_id == blk_id,
                Flat.flat_number == flat_no
            ).first()
            if not flat:
                flat = Flat(
                    society_id=soc_id,
                    block_id=blk_id,
                    flat_number=flat_no,
                    status="OCCUPIED"
                )
                db.add(flat)
                db.flush()

            # 5b. Assign User (Chairman for A-101, Member for other flats)
            if flat_no == "A-101":
                user = chairman
            else:
                member_num = idx + 1
                mobile = f"980000{member_num:04d}"
                name = MEMBER_NAMES[idx % len(MEMBER_NAMES)]
                email = f"member{member_num:02d}.{name.split()[0].lower()}@greenpalms.org"

                user = db.query(User).filter(User.mobile_number == mobile).first()
                if not user:
                    base_reading = 100 + (member_num * 10)
                    user = User(
                        name=name,
                        mobile_number=mobile,
                        email=email,
                        user_type=1,  # Member
                        society_id=soc_id,
                        block_id=blk_id,
                        flat_number=flat_no,
                        approval_status=1,
                        previous_unit=base_reading,
                        is_active=True
                    )
                    db.add(user)
                    db.flush()
                    members_created += 1

            # 5c. Create / Update Meter
            serial_no = f"MTR-{flat_no.replace('-', '')}"
            meter = db.query(Meter).filter(Meter.meter_serial_number == serial_no).first()
            if not meter:
                meter = Meter(
                    society_id=soc_id,
                    block_id=blk_id,
                    user_id=user.id,
                    flat_number=flat_no,
                    meter_serial_number=serial_no,
                    initial_reading=user.previous_unit - 40,
                    current_reading=user.previous_unit,
                    status="ACTIVE"
                )
                db.add(meter)
                db.flush()

            # 5d. Ensure EACH flat has EXACTLY 1 pending reading request (status = 0)
            pending_readings = db.query(MeterReading).filter(
                MeterReading.society_id == soc_id,
                MeterReading.user_id == user.id,
                MeterReading.status == 0
            ).all()

            if len(pending_readings) == 0:
                new_units = 20 + (idx % 25)
                new_current = user.previous_unit + new_units
                reading_pending = MeterReading(
                    society_id=soc_id,
                    user_id=user.id,
                    meter_id=meter.id,
                    block_id=blk_id,
                    previous_unit=user.previous_unit,
                    current_unit=new_current,
                    total_unit=new_units,
                    unit_price=25.00,
                    total_price=float(new_units * 25.00),
                    image_url=f"https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500",
                    status=0,  # Pending Reading Request
                    remarks=f"Monthly Water Reading submission from {flat_no}",
                    is_deletable=True,
                    created_at=datetime.now(timezone.utc) - timedelta(hours=(50 - idx))
                )
                db.add(reading_pending)
                readings_created += 1
            elif len(pending_readings) > 1:
                # Keep only 1 pending request per member
                for extra_r in pending_readings[1:]:
                    db.delete(extra_r)

        db.commit()
        print(f"Successfully seeded/verified Society '{society.name}' with 50 members, 50 flats, meters, and 50 pending reading requests (1 per member)!")
        return {
            "society_id": society.id,
            "society_name": society.name,
            "society_code": society.code,
            "chairman_mobile": chairman.mobile_number,
            "total_flats": len(flats_config),
            "members_count": len(flats_config)
        }
    except Exception as e:
        db.rollback()
        print(f"Error seeding 50 members society: {e}")
        raise e
    finally:
        if should_close:
            db.close()

if __name__ == "__main__":
    seed_society_50_members()

