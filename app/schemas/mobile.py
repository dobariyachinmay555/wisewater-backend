from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict

# Standard ApiResponseModel matching Flutter frontend
class MobileApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: int = 1
    message: str = "Success"
    data: Any = {}

class SendOtpRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "mobile_number": "9714555006",
                "device_type": "1",
                "user_type": "1"
            }
        }
    )
    mobile_number: str
    device_type: Optional[str] = "1"
    user_type: Optional[str] = None

class VerifyOtpRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "mobile_number": "9714555006",
                "otp": "839201",
                "user_type": 1,
                "fcm_token": ""
            }
        }
    )
    mobile_number: str
    otp: Optional[str] = None
    otp_code: Optional[str] = None
    device_type: Optional[str] = "1"
    device_token: Optional[str] = None
    fcm_token: Optional[str] = None
    user_type: Optional[int] = None    # None = don't enforce role check (backward compatible)
    firebase_verified: Optional[bool] = False



class UpdateApartmentDetailRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    apartment_id: int
    block_id: int
    flat_number: str
    name: str

class UpdateUnitPriceRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    unit_price: str

class UpdateBlockTitleRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    block_id: int
    title: str

class UpdatePendingRequestStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    apartment_user_id: int
    status: int  # 1: Accept, 2: Reject
    previous_unit: Optional[str] = None

class UpdateReadingRequestStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    user_unit_history_id: int
    status: int  # 1: Accept, 2: Reject

class UpdatePreviousUnitRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    apartment_user_id: str
    unit: str

class BlockConfigItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str
    total_flats: int

class SocietyRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    society_name: str
    property_category: str = "FLAT_APARTMENT"  # FLAT_APARTMENT, ROW_HOUSE
    address: str
    city: str
    state: str
    pin_code: str
    blocks: Optional[List[BlockConfigItem]] = []
    total_houses: Optional[int] = None
    chairman_name: str
    chairman_mobile: str
    chairman_email: str
    contact_number: Optional[str] = None
    society_email: Optional[str] = None
    establishment_year: Optional[int] = None
    unit_price: Optional[float] = 25.00
    photo_submission_frequency: Optional[str] = "1_MONTH"  # "1_MONTH" or "6_MONTHS"

class SocietyResubmitRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    society_name: Optional[str] = None
    property_category: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    blocks: Optional[List[BlockConfigItem]] = None
    total_houses: Optional[int] = None
    chairman_name: Optional[str] = None
    chairman_email: Optional[str] = None
    contact_number: Optional[str] = None
    society_email: Optional[str] = None
    establishment_year: Optional[int] = None
    unit_price: Optional[float] = None
    photo_submission_frequency: Optional[str] = None

class UpdateSocietyProfileRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    unit_price: Optional[float] = None
    contact_number: Optional[str] = None
    society_email: Optional[str] = None
    establishment_year: Optional[int] = None
    photo_submission_frequency: Optional[str] = None  # "1_MONTH", "6_MONTHS"

class AddMemberRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    mobile_number: str
    email: Optional[str] = None
    block_id: Optional[int] = None
    flat_number: Optional[str] = None
    house_number: Optional[str] = None
    role: Optional[int] = 1  # 1: Member, 2: Committee

class JoinSocietyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    society_id: Optional[int] = None
    society_code: Optional[str] = None
    name: str
    mobile_number: str
    email: Optional[str] = None
    block_id: Optional[int] = None
    flat_number: Optional[str] = None
    house_number: Optional[str] = None
    role: Optional[int] = 1
    initial_reading: Optional[int] = None
    image_url: Optional[str] = None

# Chairman Transfer Request Schemas
class InitiateChairmanTransferRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    new_mobile_number: str
    new_name: str
    new_email: Optional[str] = None
    demote_old_to_resident: Optional[bool] = True

class VerifyChairmanTransferOtpRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    transfer_id: str
    mobile_number: str
    otp_code: str

class CompleteChairmanTransferRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    transfer_id: str
    demote_old_to_resident: Optional[bool] = True

class VerifyAndCompleteChairmanTransferRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    transfer_id: str
    mobile_number: str
    otp_code: str
    demote_old_to_resident: Optional[bool] = True

class CancelChairmanTransferRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    transfer_id: str
    reason: Optional[str] = None

# Chairman Member Management Schemas
class ChairmanUpdateMemberRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    block_id: Optional[int] = None
    flat_number: Optional[str] = None
    is_active: Optional[bool] = None

class ChairmanChangeFlatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    target_block_id: int
    target_flat_number: str
    reason: Optional[str] = None

class ChairmanReplaceMemberRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    new_name: str
    new_mobile_number: str
    new_email: Optional[str] = None
    deactivate_old_member: Optional[bool] = False
    reason: Optional[str] = "Resident replaced"

class ChairmanRemoveMemberRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    reason: Optional[str] = "Removed by Chairman"



