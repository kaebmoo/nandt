# flask_app/app/services/sms_service.py
import os
import http.client
import ssl
import logging
from urllib.parse import quote_plus
from .redis_connection import redis_manager

# Get a logger instance
logger = logging.getLogger(__name__)

def send_otp_sms(phone_number, otp):
    """Send OTP via SMS"""
    logger.info(f"Attempting to send OTP SMS to {phone_number}")
    # ใช้ os.environ โดยตรง ไม่ต้องพึ่ง Flask
    user = os.environ.get("NT_SMS_USER")
    passw = os.environ.get("NT_SMS_PASS")
    sender = os.environ.get("NT_SMS_SENDER")
    host = os.environ.get("NT_SMS_HOST")
    api_path = os.environ.get("NT_SMS_API")

    if not all([user, passw, sender, host, api_path]):
        logger.error("SMS service is not configured. Missing one or more NT_SMS_* environment variables.")
        return False
    
    message = f"รหัส OTP ของคุณคือ {otp} (ใช้ได้ 5 นาที)"
    encoded_message = quote_plus(message)
    
    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Envelope>
        <Header/>
        <Body>
            <sendSMS>
                <user>{user}</user>
                <pass>{passw}</pass>
                <from>{sender}</from>
                <target>{phone_number}</target>
                <mess>{encoded_message}</mess>
                <lang>T</lang>
            </sendSMS>
        </Body>
    </Envelope>"""
    
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    
    try:
        context = ssl._create_unverified_context()
        conn = http.client.HTTPSConnection(host, context=context)
        # ส่ง payload เป็น bytes ที่เข้ารหัส utf-8
        conn.request("POST", api_path, payload.encode('utf-8'), headers)
        res = conn.getresponse()
        data = res.read()
        response_text = data.decode('utf-8')
        logger.info(f"SMS Response for {phone_number}: Status {res.status}, Data: {response_text}")
        return True
    except Exception as e:
        logger.error(f"SMS sending failed for {phone_number}: {e}", exc_info=True)
        return False

def queue_otp_sms(phone_number, otp):
    """Queue SMS for background sending"""
    try:
        queue = redis_manager.get_queue('default')
        job = queue.enqueue(send_otp_sms, phone_number=phone_number, otp=otp)
        logger.info(f"Queued OTP SMS job {job.id} for {phone_number}")
        return job.id
    except Exception as e:
        logger.error(f"Failed to queue OTP SMS for {phone_number}: {e}", exc_info=True)
        return None