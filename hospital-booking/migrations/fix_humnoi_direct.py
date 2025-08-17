# fix_humnoi_direct.py - แก้ไข enum โดยตรง

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# โหลด environment variables
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def fix_humnoi_direct():
    """แก้ไข enum โดยตรงใน tenant_humnoi"""
    
    print("=== Direct fix for tenant_humnoi ===")
    
    db = SessionLocal()
    
    try:
        # ตั้งค่า search_path
        db.execute(text('SET search_path TO tenant_humnoi, public'))
        
        print("Current availabilities data:")
        result = db.execute(text("SELECT id, provider_id, day_of_week FROM availabilities LIMIT 5")).fetchall()
        for r in result:
            print(f"  ID: {r[0]}, Provider: {r[1]}, Day: {r[2]}")
        
        # ตรวจสอบ enum values ที่มี
        print("\nChecking enum values in tenant_humnoi:")
        result = db.execute(text("""
            SELECT enumlabel 
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            JOIN pg_namespace n ON t.typnamespace = n.oid
            WHERE n.nspname = 'tenant_humnoi' AND t.typname = 'dayofweek'
            ORDER BY e.enumsortorder;
        """)).fetchall()
        
        enum_values = [r[0] for r in result]
        print(f"Available enum values: {enum_values}")
        
        if 'MONDAY' not in enum_values:
            print("❌ MONDAY not found in enum values!")
            
            # ดรอป table และสร้างใหม่
            print("Dropping and recreating availabilities table...")
            try:
                db.execute(text("DROP TABLE IF EXISTS availabilities CASCADE"))
                db.execute(text("DROP TYPE IF EXISTS dayofweek CASCADE"))
                
                # สร้าง enum ใหม่
                db.execute(text("""
                    CREATE TYPE dayofweek AS ENUM (
                        'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 
                        'THURSDAY', 'FRIDAY', 'SATURDAY'
                    )
                """))
                
                # สร้าง table ใหม่
                db.execute(text("""
                    CREATE TABLE availabilities (
                        id SERIAL PRIMARY KEY,
                        provider_id INTEGER NOT NULL REFERENCES providers(id),
                        event_type_id INTEGER NOT NULL REFERENCES event_types(id),
                        day_of_week dayofweek NOT NULL,
                        start_time TIME NOT NULL,
                        end_time TIME NOT NULL,
                        timezone VARCHAR(50) DEFAULT 'Asia/Bangkok',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                print("✅ Recreated availabilities table with correct enum")
                
            except Exception as e:
                print(f"❌ Error recreating table: {e}")
                raise
        
        db.commit()
        print("✅ Direct fix completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

if __name__ == "__main__":
    fix_humnoi_direct()