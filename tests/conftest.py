import pytest
from app.core.database import SessionLocal
from app.models.society import Society, Block, Flat
from app.models.user import User
from app.models.meter import Meter
from app.models.reading import MeterReading
from app.models.billing import Bill
from app.models.audit import AuditLog

@pytest.fixture(scope="session", autouse=True)
def clean_test_artifacts():
    """Run before and after all test suites to ensure test runs leave the database clean with only SOC-GP50."""
    def cleanup():
        db = SessionLocal()
        try:
            test_societies = db.query(Society).filter(Society.code != 'SOC-GP50').all()
            for s in test_societies:
                db.query(Bill).filter(Bill.society_id == s.id).delete(synchronize_session=False)
                db.query(MeterReading).filter(MeterReading.society_id == s.id).delete(synchronize_session=False)
                db.query(Meter).filter(Meter.society_id == s.id).delete(synchronize_session=False)
                db.query(User).filter(User.society_id == s.id).delete(synchronize_session=False)
                db.query(Flat).filter(Flat.society_id == s.id).delete(synchronize_session=False)
                db.query(Block).filter(Block.society_id == s.id).delete(synchronize_session=False)
                db.query(AuditLog).filter(AuditLog.society_id == s.id).delete(synchronize_session=False)
                db.delete(s)
            db.commit()
            
            # Reset SOC-GP50 readings to clean baseline (50 pending requests, 0 bills)
            from app.seed_society_50 import seed_society_50_members
            db.query(Bill).delete(synchronize_session=False)
            db.query(MeterReading).delete(synchronize_session=False)
            seed_society_50_members(db=db)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    cleanup()
    yield
    cleanup()
