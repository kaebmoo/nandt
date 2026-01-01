# hospital-booking/shared_db/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from flask import g
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Declarative Bases ---
# สร้าง Base แยกสำหรับ public และ tenant schemas ตามโครงสร้างใน models.py
PublicBase = declarative_base()
TenantBase = declarative_base()

# --- Session Helper ---
def get_db_session():
    """
    ดึง database session สำหรับ request ปัจจุบันจาก `g` object ของ Flask
    หากยังไม่มี session จะทำการสร้างใหม่และผูกไว้กับ `g`
    """
    if 'db' not in g or g.db is None:
        g.db = SessionLocal()
    return g.db