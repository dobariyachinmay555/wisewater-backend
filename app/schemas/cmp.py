from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, Field

class CMPLoginRequest(BaseModel):
    email: EmailStr
    password: str

class CMPLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff: Dict[str, Any]

class CreateSocietyRequest(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    unit_price: float = 25.00
    chairman_name: str
    chairman_mobile: str
    chairman_email: Optional[EmailStr] = None
    number_of_blocks: int = 2
    flats_per_block: int = 20
    subscription_plan_id: Optional[str] = None

class UpdateSocietyRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    unit_price: Optional[float] = None
    status: Optional[str] = None  # ACTIVE, SUSPENDED, ARCHIVED
    chairman_name: Optional[str] = None
    chairman_mobile: Optional[str] = None
    chairman_email: Optional[EmailStr] = None

class CreateStaffRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "SUPPORT"  # OWNER, SUPER_ADMIN, ADMIN, SUPPORT, FINANCE, READ_ONLY

class UpdateReadingStatusCMPRequest(BaseModel):
    status: int  # 1: Approved, 2: Rejected, 3: Flagged
    remarks: Optional[str] = None

class GenerateMonthlyBillsRequest(BaseModel):
    society_id: int
    billing_month: int
    billing_year: int

class RejectRegistrationRequest(BaseModel):
    reason: str

class RequestChangesRequest(BaseModel):
    notes: str

