import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
# Config settings loaded with .env
from pydantic import Field

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BACKEND_DIR, ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=ENV_PATH if os.path.exists(ENV_PATH) else ".env",
        env_file_encoding="utf-8",
        extra="allow"
    )
    
    PROJECT_NAME: str = "WiseWater API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    
    # Security
    SECRET_KEY: str = Field(
        default="e7b39a8c2f1d4e6b8a0c2e4f6a8b0c2e4f6a8b0c2e4f6a8b0c2e4f6a8b0c2e4f"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    CMP_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours for admin sessions
    
    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./wisewater.db"
    )
    
    # Uploads
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
    MAX_UPLOAD_SIZE_MB: int = 15

    # SMS Gateway Configuration
    SMS_PROVIDER: str = Field(default="fast2sms")  # Options: fast2sms, twilio, msg91, mock
    ENABLE_TEST_OTP_BYPASS: bool = Field(default=True)  # Enabled for development/testing convenience
    
    # Fast2SMS (India)
    FAST2SMS_API_KEY: str = Field(default="")
    
    # Twilio (Global)
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_PHONE_NUMBER: str = Field(default="")
    
    # MSG91 (India)
    MSG91_AUTH_KEY: str = Field(default="")
    MSG91_TEMPLATE_ID: str = Field(default="")
    
    # Firebase Cloud Messaging (FCM) Push Notifications
    # Path to service account JSON (e.g. "firebase-service-account.json") or raw JSON string
    FIREBASE_CREDENTIALS_PATH: str = Field(default="")
    FIREBASE_CREDENTIALS_JSON: str = Field(default="")

settings = Settings()
