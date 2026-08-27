import os
from datetime import datetime, timezone
from app.core.database import engine, Base, SessionLocal
from app.core.security import get_password_hash
from app.models import (
    CompanyStaff, SubscriptionPlan, Society, Block, User,
    Meter, MeterReading, Bill, AuditLog
)

def seed_database():
    """Create all tables and seed only system accounts and subscription plans (Clean Production Baseline)."""
    print("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Company Staff (CMP Login)
        if not db.query(CompanyStaff).filter(CompanyStaff.email == "admin@wisewater.com").first():
            print("Seeding Company Staff Super Admin...")
            admin = CompanyStaff(
                name="WiseWater Platform Owner",
                email="admin@wisewater.com",
                password_hash=get_password_hash("admin123"),
                role="OWNER",
                is_active=True
            )
            db.add(admin)
            
            support = CompanyStaff(
                name="Customer Support Lead",
                email="support@wisewater.com",
                password_hash=get_password_hash("support123"),
                role="SUPPORT",
                is_active=True
            )
            db.add(support)

        # 2. Subscription Plans
        if not db.query(SubscriptionPlan).first():
            print("Seeding Subscription Plans...")
            plan_trial = SubscriptionPlan(
                name="Starter Trial",
                plan_type="TRIAL",
                price_per_flat=0.00,
                base_price=0.00,
                max_flats=50,
                features={"reports": True, "support": "Standard"}
            )
            plan_monthly = SubscriptionPlan(
                name="Standard Monthly",
                plan_type="MONTHLY",
                price_per_flat=15.00,
                base_price=300.00,
                max_flats=200,
                features={"reports": True, "support": "Priority", "custom_unit_price": True}
            )
            plan_annual = SubscriptionPlan(
                name="Enterprise Annual",
                plan_type="ANNUAL",
                price_per_flat=12.00,
                base_price=3000.00,
                max_flats=1000,
                features={"reports": True, "support": "24/7 Dedicated", "custom_unit_price": True, "ocr": True}
            )
            db.add_all([plan_trial, plan_monthly, plan_annual])
            db.flush()

        # 3. Initial Audit Log
        if not db.query(AuditLog).first():
            print("Seeding Initial Audit Log...")
            audit = AuditLog(
                actor_type="SYSTEM",
                actor_id="system-init",
                actor_email="system@wisewater.com",
                action="INITIALIZE_PLATFORM",
                entity_type="SYSTEM",
                entity_id="1",
                before_state=None,
                after_state={"status": "INITIALIZED", "version": "1.0.0"},
                ip_address="127.0.0.1"
            )
            db.add(audit)

        # 4. Seed Society with 50 Members
        from app.seed_society_50 import seed_society_50_members
        seed_society_50_members(db=db)

        db.commit()
        print("Clean database initialized and seeded successfully with 50-member society!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
