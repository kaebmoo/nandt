# core/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# สร้าง engine
engine = create_engine(settings.DATABASE_URL)

# สร้าง SessionLocal class สำหรับใช้สร้าง session ในแต่ละ request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# สร้าง Base class สำหรับให้ Models ต่างๆ kế thừa (inherit)
Base = declarative_base()

# สร้าง dependency function สำหรับให้ FastAPI เรียกใช้
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()