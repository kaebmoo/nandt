# config.py
import os
from dotenv import load_dotenv

# โหลดตัวแปรจาก .env file
load_dotenv()

# ตัวแปรสำหรับการเชื่อมต่อ TeamUp API
TEAMUP_API_KEY = os.getenv('TEAMUP_API')
CALENDAR_ID = os.getenv('CALENDAR_ID')

# ตั้งค่าแอปพลิเคชัน Flask
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dialysis_scheduler_secret_key')
    DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit for file uploads
    
    # ตั้งค่าโฟลเดอร์ uploads
    @staticmethod
    def init_app():
        if not os.path.exists(Config.UPLOAD_FOLDER):
            os.makedirs(Config.UPLOAD_FOLDER)