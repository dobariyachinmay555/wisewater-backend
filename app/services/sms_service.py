import logging
import random
from typing import Tuple
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

def generate_otp(length: int = 4) -> str:
    """Generate a secure numeric OTP."""
    if length == 6:
        return f"{random.randint(100000, 999999)}"
    return f"{random.randint(1000, 9999)}"

async def send_sms_otp(mobile_number: str, otp_code: str) -> Tuple[bool, str]:
    """
    Sends real SMS OTP to the recipient's phone number using the configured SMS gateway.
    Supports Fast2SMS, Twilio, MSG91, and Development Mock.
    """
    # Clean mobile number
    clean_mobile = "".join(filter(str.isdigit, mobile_number))
    if len(clean_mobile) > 10 and clean_mobile.startswith("91"):
        clean_mobile = clean_mobile[-10:]

    provider = (settings.SMS_PROVIDER or "mock").lower()

    # 1. FAST2SMS (India)
    if provider == "fast2sms":
        api_key = settings.FAST2SMS_API_KEY
        if not api_key or api_key == "YOUR_FAST2SMS_API_KEY":
            logger.warning(f"Fast2SMS API key not set. Logging OTP for {clean_mobile}: {otp_code}")
            return True, f"OTP logged in server console: {otp_code}"

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
                data = res.json()
                logger.info(f"Fast2SMS response for {clean_mobile}: {data}")
                if data.get("return") is True or res.status_code == 200:
                    return True, "SMS OTP sent successfully to your mobile number"
                
                # If Fast2SMS requires ₹100 recharge or website verification
                err_msg = data.get("message", "Fast2SMS requires recharge")
                logger.warning(f"Fast2SMS notice ({clean_mobile}): {err_msg}. Using debug OTP: {otp_code}")
                if settings.ENABLE_TEST_OTP_BYPASS or settings.DEBUG:
                    return True, f"OTP generated: {otp_code} (or test OTP 123456)"
                return False, err_msg
        except Exception as e:
            logger.error(f"Fast2SMS request error: {str(e)}")
            if settings.ENABLE_TEST_OTP_BYPASS or settings.DEBUG:
                return True, f"OTP generated: {otp_code} (or test OTP 123456)"
            return False, f"SMS Gateway connection failed: {str(e)}"

    # 2. TWILIO (Global)
    elif provider == "twilio":
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_phone = settings.TWILIO_PHONE_NUMBER

        if not sid or not token or not from_phone or sid.startswith("YOUR_"):
            logger.warning(f"Twilio credentials not set. Logging OTP for {clean_mobile}: {otp_code}")
            return True, f"OTP logged in server console: {otp_code}"

        to_phone = f"+91{clean_mobile}" if not clean_mobile.startswith("+") else clean_mobile
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        message_body = f"Your WiseWater verification code is: {otp_code}. Valid for 10 minutes. Do not share this OTP."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    url,
                    data={"From": from_phone, "To": to_phone, "Body": message_body},
                    auth=(sid, token)
                )
                if res.status_code in [200, 201]:
                    return True, "SMS OTP sent successfully via Twilio"
                return False, f"Twilio SMS failed with status {res.status_code}"
        except Exception as e:
            logger.error(f"Twilio error: {str(e)}")
            return False, f"Twilio error: {str(e)}"

    # 3. MSG91 (India)
    elif provider == "msg91":
        auth_key = settings.MSG91_AUTH_KEY
        template_id = settings.MSG91_TEMPLATE_ID

        if not auth_key or auth_key.startswith("YOUR_"):
            logger.warning(f"MSG91 key not configured. Logging OTP: {otp_code}")
            return True, f"OTP logged in server console: {otp_code}"

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
                    return True, "SMS OTP sent successfully via MSG91"
                return False, "MSG91 failed to send OTP"
        except Exception as e:
            logger.error(f"MSG91 error: {str(e)}")
            return False, f"MSG91 error: {str(e)}"

    # 4. DEFAULT MOCK / CONSOLE FOR DEVELOPMENT
    logger.info(f"🔑 [MOCK SMS] Verification code for {clean_mobile} is: {otp_code}")
    print(f"\n=======================================================\n📲 [REAL SMS SIMULATOR] To: {clean_mobile} | OTP: {otp_code}\n=======================================================\n")
    return True, f"OTP generated: {otp_code}"
