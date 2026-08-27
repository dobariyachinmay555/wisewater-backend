import os
import time
import subprocess
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base
# WiseWater FastAPI Application (Reload triggered)
from app.seed import seed_database

# Import Mobile API Routers
from app.api.v1.mobile.auth import router as mobile_auth_router
from app.api.v1.mobile.profile import router as mobile_profile_router
from app.api.v1.mobile.society import router as mobile_society_router
from app.api.v1.mobile.readings import router as mobile_readings_router
from app.api.v1.mobile.admin import router as mobile_admin_router
from app.api.v1.mobile.onboarding import router as mobile_onboarding_router
from app.api.v1.mobile.chairman import router as mobile_chairman_router

# Import CMP API Routers
from app.api.v1.cmp.auth import router as cmp_auth_router
from app.api.v1.cmp.dashboard import router as cmp_dashboard_router
from app.api.v1.cmp.societies import router as cmp_societies_router
from app.api.v1.cmp.users import router as cmp_users_router
from app.api.v1.cmp.readings import router as cmp_readings_router
from app.api.v1.cmp.billing import router as cmp_billing_router
from app.api.v1.cmp.audit import router as cmp_audit_router
from app.api.v1.cmp.staff import router as cmp_staff_router

def adb_keepalive():
    adb_candidates = [
        r"C:\src\platform-tools\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        "adb"
    ]
    adb_path = "adb"
    for candidate in adb_candidates:
        if os.path.exists(candidate):
            adb_path = candidate
            break
            
    while True:
        try:
            subprocess.run([adb_path, "reverse", "tcp:8000", "tcp:8000"], capture_output=True)
        except Exception:
            pass
        time.sleep(4)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and seed
    Base.metadata.create_all(bind=engine)
    try:
        seed_database()
    except Exception as e:
        print(f"Database init note: {e}")
    if settings.DEBUG and settings.ENVIRONMENT == "development":
        threading.Thread(target=adb_keepalive, daemon=True).start()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists and mount static route
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# 1. Register Mobile API Routers
app.include_router(mobile_auth_router, prefix="/api", tags=["Mobile Auth"])
app.include_router(mobile_profile_router, prefix="/api", tags=["Mobile Profile"])
app.include_router(mobile_society_router, prefix="/api", tags=["Mobile Society"])
app.include_router(mobile_readings_router, prefix="/api", tags=["Mobile Readings"])
app.include_router(mobile_admin_router, prefix="/api", tags=["Mobile Admin"])
app.include_router(mobile_onboarding_router, prefix="/api", tags=["Mobile Onboarding"])
app.include_router(mobile_chairman_router, prefix="/api", tags=["Mobile Chairman"])

# 2. Register Company Master Panel (CMP) Routers
app.include_router(cmp_auth_router, prefix="/api/v1/cmp/auth", tags=["CMP Auth"])
app.include_router(cmp_dashboard_router, prefix="/api/v1/cmp/dashboard", tags=["CMP Dashboard"])
app.include_router(cmp_societies_router, prefix="/api/v1/cmp/societies", tags=["CMP Societies"])
app.include_router(cmp_users_router, prefix="/api/v1/cmp/users", tags=["CMP Users"])
app.include_router(cmp_readings_router, prefix="/api/v1/cmp/readings", tags=["CMP Readings"])
app.include_router(cmp_billing_router, prefix="/api/v1/cmp/billing", tags=["CMP Billing"])
app.include_router(cmp_audit_router, prefix="/api/v1/cmp/audit-logs", tags=["CMP Audit Logs"])
app.include_router(cmp_staff_router, prefix="/api/v1/cmp/staff", tags=["CMP Staff"])

# Mount CMP Web App if dist exists
cmp_dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cmp-web", "dist"))
if os.path.exists(cmp_dist_path):
    app.mount("/cmp", StaticFiles(directory=cmp_dist_path, html=True), name="cmp")

@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": "WiseWater Production REST API & CMP Gateway",
        "version": settings.VERSION,
        "cmp_panel": "/cmp"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
