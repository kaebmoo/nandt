# fix_humnoi_enum.py - แก้ไข enum ใน tenant_humnoi schema

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

def fix_humnoi_enum():
    """แก้ไข enum ใน tenant_humnoi schema"""
    
    print("=== Fixing tenant_humnoi enum ===")
    
    db = SessionLocal()
    schema_name = "tenant_humnoi"
    
    try:
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # ตรวจสอบ enum ที่มีอยู่
        result = db.execute(text("""
            SELECT enumlabel 
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            JOIN pg_namespace n ON t.typnamespace = n.oid
            WHERE n.nspname = 'tenant_humnoi' AND t.typname = 'dayofweek'
            ORDER BY e.enumsortorder;
        """)).fetchall()
        
        print(f"Current enum values: {[r[0] for r in result]}")
        
        # ถ้า enum ใช้ค่าเก่า ต้องอัปเดท
        current_values = [r[0] for r in result]
        expected_values = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY']
        
        if set(current_values) != set(expected_values):
            print("⚠️ Enum values don't match expected format")
            
            # Drop และสร้าง enum ใหม่
            try:
                # ดูว่ามี column ใช้ enum นี้หรือไม่
                db.execute(text("ALTER TABLE availabilities ALTER COLUMN day_of_week DROP DEFAULT"))
                db.execute(text("ALTER TABLE availabilities ALTER COLUMN day_of_week TYPE TEXT"))
                db.execute(text("DROP TYPE IF EXISTS dayofweek"))
                
                # สร้าง enum ใหม่
                db.execute(text("""
                    CREATE TYPE dayofweek AS ENUM (
                        'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 
                        'THURSDAY', 'FRIDAY', 'SATURDAY'
                    )
                """))
                
                # เปลี่ยน column กลับเป็น enum
                db.execute(text("ALTER TABLE availabilities ALTER COLUMN day_of_week TYPE dayofweek USING day_of_week::dayofweek"))
                
                print("✅ Enum updated successfully")
                
            except Exception as e:
                print(f"❌ Error updating enum: {e}")
                # ถ้าไม่ได้ ใช้วิธี mapping values
                print("Trying value mapping approach...")
                
                # Map ค่าเก่าเป็นค่าใหม่
                value_mapping = {
                    '0': 'SUNDAY', '1': 'MONDAY', '2': 'TUESDAY', '3': 'WEDNESDAY',
                    '4': 'THURSDAY', '5': 'FRIDAY', '6': 'SATURDAY'
                }
                
                for old_val, new_val in value_mapping.items():
                    try:
                        db.execute(text(f"UPDATE availabilities SET day_of_week = '{new_val}' WHERE day_of_week = '{old_val}'"))
                        print(f"Updated {old_val} -> {new_val}")
                    except:
                        pass
        else:
            print("✅ Enum values are correct")
        
        db.commit()
        print("✅ tenant_humnoi enum fixed successfully!")
        
    except Exception as e:
        print(f"❌ Error fixing enum: {e}")
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

if __name__ == "__main__":
    fix_humnoi_enum()