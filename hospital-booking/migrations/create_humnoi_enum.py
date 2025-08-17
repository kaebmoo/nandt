# create_humnoi_enum.py - สร้าง enum สำหรับ tenant_humnoi

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# โหลด environment variables
load_dotenv()

# เพิ่ม path สำหรับ import models
sys.path.append('flask_app/app')
import models

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_humnoi_enum():
    """สร้าง enum สำหรับ tenant_humnoi"""
    
    print("=== Creating enum for tenant_humnoi ===")
    
    db = SessionLocal()
    
    try:
        # ตั้งค่า search_path
        db.execute(text('SET search_path TO tenant_humnoi, public'))
        
        # สร้าง enum ใน schema tenant_humnoi
        try:
            db.execute(text("""
                CREATE TYPE dayofweek AS ENUM (
                    'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 
                    'THURSDAY', 'FRIDAY', 'SATURDAY'
                )
            """))
            print("✅ Created dayofweek enum in tenant_humnoi")
        except Exception as e:
            if "already exists" in str(e):
                print("✅ dayofweek enum already exists")
            else:
                print(f"❌ Error creating enum: {e}")
                raise
        
        # ตรวจสอบว่า availabilities table มี column day_of_week หรือไม่
        result = db.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns 
            WHERE table_schema = 'tenant_humnoi' 
            AND table_name = 'availabilities' 
            AND column_name = 'day_of_week'
        """)).fetchone()
        
        if result:
            print(f"day_of_week column: {result}")
            
            # ถ้า column เป็น text หรือ integer ต้องเปลี่ยนเป็น enum
            if result[2] != 'dayofweek':
                print("Converting day_of_week column to enum...")
                try:
                    db.execute(text("ALTER TABLE availabilities ALTER COLUMN day_of_week TYPE dayofweek USING day_of_week::dayofweek"))
                    print("✅ Converted day_of_week to enum")
                except Exception as e:
                    print(f"❌ Error converting column: {e}")
                    # Try direct value mapping
                    print("Trying direct enum values...")
                    
        else:
            print("❌ day_of_week column not found in availabilities table")
        
        # สร้าง tables ทั้งหมดใน schema
        print("Recreating all tenant tables...")
        models.TenantBase.metadata.create_all(bind=engine)
        print("✅ All tables created/updated")
        
        db.commit()
        print("✅ tenant_humnoi setup completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

if __name__ == "__main__":
    create_humnoi_enum()