import logging
import secrets
from typing import Tuple, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

def generate_otp(length: int = 6) -> str:
    """
    Generate a cryptographically secure numeric OTP using Python's secrets module.
    Default length is 6 digits (between 100000 and 999999).
    """
    if length <= 0:
        length = 6
    min_val = 10 ** (length - 1)
    max_range = 9 * min_val
    code_int = secrets.randbelow(max_range) + min_val
    return str(code_int)

def normalize_indian_mobile(mobile_number: str) -> Optional[str]:
    """
    Normalizes Indian mobile numbers into standard 10-digit string.
    Accepts:
      - 10-digit number (e.g. 9876543210)
      - 919876543210
      - +919876543210
      - 09876543210
    Returns normalized 10-digit string or None if invalid.
    """
    if not mobile_number:
        return None
    
    clean_digits = "".join(filter(str.isdigit, str(mobile_number).strip()))
    
    # +91 or 91 prefix (12 digits total)
    if len(clean_digits) == 12 and clean_digits.startswith("91"):
        clean_digits = clean_digits[2:]
    # Leading 0 prefix (11 digits total)
    elif len(clean_digits) == 11 and clean_digits.startswith("0"):
        clean_digits = clean_digits[1:]
        
    if len(clean_digits) == 10 and clean_digits[0] in "6789":
        return clean_digits
    elif len(clean_digits) == 10:
        return clean_digits
    
    return None

async def send_sms_otp(mobile_number: str, otp_code: str) -> Tuple[bool, str]:
    """
    Sends real SMS OTP to the recipient's phone number using the configured SMS gateway.
    Supports Fast2SMS (India Quick OTP), Twilio, and MSG91.
    Never returns fake success when SMS delivery fails.
    """
    clean_mobile = normalize_indian_mobile(mobile_number)
    if not clean_mobile:
        return False, "Please enter a valid 10-digit Indian mobile number."

    provider = (settings.SMS_PROVIDER or "fast2sms").lower().strip()

    # 1. FAST2SMS (India)
    if provider == "fast2sms":
        api_key = (settings.FAST2SMS_API_KEY or "").strip()
        if not api_key or api_key == "YOUR_FAST2SMS_API_KEY":
            logger.error("Fast2SMS API key is not configured in environment variables.")
            return False, "SMS service is not configured. Please contact support."

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "route": "otp",
            "variables_values": otp_code,
            "numbers": clean_mobile
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                
                # Log safe diagnostic information only (no OTP, no API keys)
                masked_mobile = f"{clean_mobile[:2]}******{clean_mobile[-2:]}"
                is_success = res.status_code == 200 and data.get("return") is True
                
                if is_success:
                    logger.info(f"Fast2SMS OTP sent successfully to {masked_mobile}")
                    return True, "OTP sent successfully to your mobile number via SMS."
                
                err_msg = data.get("message") or f"Gateway returned status {res.status_code}"
                logger.error(f"Fast2SMS delivery failed for {masked_mobile}: {err_msg}")
                return False, "Unable to send OTP via SMS. Please check your number or try again later."
        except Exception as e:
            logger.error(f"Fast2SMS connection error: {type(e).__name__}")
            return False, "SMS gateway connection failed. Please try again."

    # 2. TWILIO (Global)
    elif provider == "twilio":
        sid = (settings.TWILIO_ACCOUNT_SID or "").strip()
        token = (settings.TWILIO_AUTH_TOKEN or "").strip()
        from_phone = (settings.TWILIO_PHONE_NUMBER or "").strip()

        if not sid or not token or not from_phone or sid.startswith("YOUR_"):
            logger.error("Twilio credentials not configured in environment variables.")
            return False, "SMS service is not configured."

        to_phone = f"+91{clean_mobile}"
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        message_body = f"Your WiseWater verification code is {otp_code}. Valid for 10 minutes. Do not share this OTP."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    url,
                    data={"From": from_phone, "To": to_phone, "Body": message_body},
                    auth=(sid, token)
                )
                if res.status_code in [200, 201]:
                    return True, "OTP sent successfully via Twilio."
                logger.error(f"Twilio error: HTTP {res.status_code}")
                return False, "Unable to send OTP. Please try again."
        except Exception as e:
            logger.error(f"Twilio exception: {type(e).__name__}")
            return False, "SMS gateway error. Please try again."

    # 3. MSG91 (India)
    elif provider == "msg91":
        auth_key = (settings.MSG91_AUTH_KEY or "").strip()
        template_id = (settings.MSG91_TEMPLATE_ID or "").strip()

        if not auth_key or auth_key.startswith("YOUR_"):
            logger.error("MSG91 key not configured in environment variables.")
            return False, "SMS service is not configured."

        url = "https://control.msg91.com/api/v5/otp"
        headers = {"authkey": auth_key, "Content-Type": "application/json"}
        params = {
            "template_id": template_id,
            "mobile": f"91{clean_mobile}",
            "otp": otp_code
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, params=params)
                if res.status_code == 200:
                    return True, "OTP sent successfully via MSG91."
                logger.error(f"MSG91 error: HTTP {res.status_code}")
                return False, "Unable to send OTP via MSG91."
        except Exception as e:
            logger.error(f"MSG91 exception: {type(e).__name__}")
            return False, "SMS gateway connection failed."

    # 4. MOCK PROVIDER (Only for controlled unit testing if explicitly configured)
    elif provider == "mock" and settings.ENABLE_TEST_OTP_BYPASS:
        logger.info(f"Mock SMS provider simulated OTP send to mobile ending in {clean_mobile[-4:]}")
        return True, "OTP sent successfully."

    return False, f"Unsupported or unconfigured SMS provider: {provider}"

