"""
Configuration module for Telegram Bot
Loads environment variables and provides configuration settings
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Main configuration class"""

    # Telegram Bot Settings
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required in .env file")

    # FastAPI Backend Settings
    FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")

    # Default Hospital
    DEFAULT_SUBDOMAIN = os.getenv("DEFAULT_SUBDOMAIN", "humnoi")

    # Redis Settings
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Conversation States
    class ConversationStates:
        """Conversation state constants"""
        # Registration states
        REGISTRATION_NAME = 0
        REGISTRATION_PHONE = 1
        REGISTRATION_OTP = 2

        # Booking states
        SELECTING_SERVICE = 10
        SELECTING_DATE = 11
        SELECTING_TIME = 12
        CONFIRMING_BOOKING = 13

        # Cancel/Reschedule states
        SELECTING_APPOINTMENT = 20
        CONFIRMING_CANCEL = 21
        CANCEL_REASON = 22
        RESCHEDULE_DATE = 23
        RESCHEDULE_TIME = 24
        CONFIRMING_RESCHEDULE = 25

    # Message Templates (Thai language)
    class Messages:
        WELCOME = """
สวัสดีครับ! ยินดีต้อนรับสู่ระบบจองนัดหมาย 🏥

คุณสามารถใช้คำสั่งต่อไปนี้:
/book - จองนัดหมาย
/myappointments - ดูนัดหมายของฉัน
/help - ดูคำสั่งทั้งหมด
/cancel - ยกเลิกการทำงานปัจจุบัน
"""

        REGISTRATION_START = """
เพื่อใช้งานระบบ กรุณาลงทะเบียนข้อมูลของคุณ

กรุณาระบุชื่อ-นามสกุลของคุณ:
"""

        REGISTRATION_PHONE = """
กรุณาระบุเบอร์โทรศัพท์ของคุณ:

คุณสามารถกดปุ่ม "แชร์เบอร์โทร" ด้านล่าง
หรือพิมพ์เบอร์โทร (รูปแบบ: 0812345678)
"""

        BOOKING_SELECT_SERVICE = """
กรุณาเลือกบริการที่ต้องการจอง:
"""

        BOOKING_SELECT_DATE = """
กรุณาเลือกวันที่ต้องการจอง:
"""

        BOOKING_SELECT_TIME = """
กรุณาเลือกเวลาที่ต้องการ:
"""

        BOOKING_CONFIRM = """
กรุณายืนยันข้อมูลการจอง:

📋 บริการ: {service}
📅 วันที่: {date}
🕐 เวลา: {time}
👤 ชื่อ: {name}
📱 เบอร์โทร: {phone}

ยืนยันการจอง?
"""

        BOOKING_SUCCESS = """
✅ จองนัดสำเร็จ!

🎫 รหัสการจอง: {reference}
📋 บริการ: {service}
📅 วันที่: {date}
🕐 เวลา: {time}
👨‍⚕️ แพทย์/พนักงาน: {provider}

📍 สถานที่: {location}

กรุณามาตามเวลานัด หากต้องการเปลี่ยนแปลง
ใช้คำสั่ง /myappointments
"""

        NO_APPOINTMENTS = """
คุณยังไม่มีนัดหมาย

ใช้คำสั่ง /book เพื่อจองนัดหมาย
"""

        ERROR_GENERIC = """
❌ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง

หากปัญหายังคงอยู่ กรุณาติดต่อเจ้าหน้าที่
"""

        CANCEL_OPERATION = """
ยกเลิกการทำงานแล้ว

ใช้ /help เพื่อดูคำสั่งที่ใช้งานได้
"""


# Create a singleton instance
config = Config()
