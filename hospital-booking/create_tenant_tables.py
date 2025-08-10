# create_tenant_tables.py - Script สร้าง tenant tables สำหรับ hospital booking system

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

def create_tenant_tables(subdomain):
    """สร้าง tenant tables สำหรับ subdomain ที่กำหนด"""
    
    print(f"=== Creating Tenant Tables for: {subdomain} ===")
    
    db = SessionLocal()
    schema_name = f"tenant_{subdomain}"
    
    try:
        # หา hospital จาก subdomain
        hospital = db.query(models.Hospital).filter_by(subdomain=subdomain).first()
        
        if not hospital:
            print(f"❌ Hospital with subdomain '{subdomain}' not found")
            # สร้าง hospital record ใหม่
            hospital = models.Hospital(
                name=f"Demo Hospital ({subdomain})",
                subdomain=subdomain,
                schema_name=schema_name
            )
            db.add(hospital)
            db.commit()
            print(f"✅ Created hospital record for '{subdomain}'")
        
        print(f"🏥 Hospital: {hospital.name}")
        print(f"📂 Schema: {schema_name}")
        
        # สร้าง schema ถ้ายังไม่มี
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        print(f"✅ Schema '{schema_name}' created/verified")
        
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # สร้าง tables ทั้งหมดที่ใช้ TenantBase
        models.TenantBase.metadata.create_all(bind=engine)
        print("✅ All tenant tables created")
        
        # ตรวจสอบ tables ที่สร้างแล้ว
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tenant_tables = inspector.get_table_names(schema=schema_name)
        print(f"📋 Created tables: {', '.join(tenant_tables)}")
        
        # สร้างข้อมูลเริ่มต้น
        create_initial_data(db)
        
        db.commit()
        print(f"✅ Tenant setup complete for '{subdomain}'!")
        
    except Exception as e:
        print(f"❌ Error creating tenant tables: {e}")
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

def create_initial_data(db):
    """สร้างข้อมูลเริ่มต้นสำหรับ tenant"""
    
    print("\n📝 Creating initial data...")
    
    try:
        # สร้าง default provider
        provider_exists = db.execute(text("SELECT COUNT(*) FROM providers")).scalar()
        
        if provider_exists == 0:
            db.execute(text("""
                INSERT INTO providers (name, title, department, is_active, public_booking_url, bio)
                VALUES 
                    ('นพ.สมชาย ใจดี', 'นพ.', 'แพทย์ทั่วไป', true, 'dr-somchai', 'แพทย์ผู้เชี่ยวชาญด้านการดูแลสุขภาพทั่วไป'),
                    ('พญ.สมหญิง สวยงาม', 'พญ.', 'กุมารเวชกรรม', true, 'dr-somying', 'แพทย์เด็กที่มีประสบการณ์มากกว่า 10 ปี')
            """))
            print("✅ Default providers created")
        
        # สร้าง default event types
        event_type_exists = db.execute(text("SELECT COUNT(*) FROM event_types")).scalar()
        
        if event_type_exists == 0:
            db.execute(text("""
                INSERT INTO event_types (name, slug, description, duration_minutes, color, is_active, buffer_before_minutes, buffer_after_minutes, min_notice_hours, max_advance_days)
                VALUES 
                    ('ตรวจสุขภาพทั่วไป', 'general-checkup', 'การตรวจสุขภาพพื้นฐานและให้คำปรึกษา', 30, '#6366f1', true, 10, 10, 4, 60),
                    ('ปรึกษาแพทย์เฉพาะทาง', 'specialist-consult', 'การปรึกษาแพทย์ผู้เชี่ยวชาญ', 45, '#10b981', true, 15, 15, 24, 90),
                    ('ตรวจเด็ก', 'child-checkup', 'การตรวจสุขภาพและวัคซีนสำหรับเด็ก', 30, '#f59e0b', true, 10, 10, 4, 30),
                    ('ตรวจประจำปี', 'annual-checkup', 'การตรวจสุขภาพประจำปีแบบครบถ้วน', 60, '#ef4444', true, 15, 15, 48, 120)
            """))
            print("✅ Default event types created")
        
        # Commit ข้อมูลก่อนสร้าง foreign key references
        db.commit()
        
        # สร้าง default availability สำหรับวันจันทร์-ศุกร์
        availability_exists = db.execute(text("SELECT COUNT(*) FROM availabilities")).scalar()
        
        if availability_exists == 0:
            # ดึง actual provider IDs ที่สร้างแล้ว
            provider_ids = db.execute(text("SELECT id FROM providers ORDER BY id")).fetchall()
            event_type_ids = db.execute(text("SELECT id FROM event_types ORDER BY id")).fetchall()
            
            if provider_ids and event_type_ids:
                provider1_id = provider_ids[0][0]
                provider2_id = provider_ids[1][0] if len(provider_ids) > 1 else provider1_id
                event_type1_id = event_type_ids[0][0]
                event_type3_id = event_type_ids[2][0] if len(event_type_ids) > 2 else event_type1_id
                
                # สำหรับ provider 1 (นพ.สมชาย) - ใช้ enum values ที่ถูกต้อง
                day_names = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY']
                for day_name in day_names:
                    db.execute(text(f"""
                        INSERT INTO availabilities (provider_id, event_type_id, day_of_week, start_time, end_time, timezone, is_active)
                        VALUES 
                            ({provider1_id}, {event_type1_id}, '{day_name}', '08:30', '16:30', 'Asia/Bangkok', true)
                    """))
                
                # สำหรับ provider 2 (พญ.สมหญิง) - เฉพาะ child checkup
                for day_name in day_names:
                    db.execute(text(f"""
                        INSERT INTO availabilities (provider_id, event_type_id, day_of_week, start_time, end_time, timezone, is_active)
                        VALUES 
                            ({provider2_id}, {event_type3_id}, '{day_name}', '09:00', '15:00', 'Asia/Bangkok', true)
                    """))
                
                print("✅ Default availability created")
            else:
                print("⚠️ No providers or event types found, skipping availability")
        
        # สร้างผู้ป่วยตัวอย่าง
        patient_exists = db.execute(text("SELECT COUNT(*) FROM patients")).scalar()
        
        if patient_exists == 0:
            db.execute(text("""
                INSERT INTO patients (name, phone_number, email)
                VALUES 
                    ('สมชาย ใจดี', '0812345678', 'somchai@email.com'),
                    ('สมหญิง สวยงาม', '0823456789', 'somying@email.com'),
                    ('น้องมินิ สุขใจ', '0834567890', 'mini@email.com')
            """))
            print("✅ Sample patients created")
            
    except Exception as e:
        print(f"❌ Error creating initial data: {e}")
        raise

def main():
    """ฟังก์ชันหลัก"""
    
    print("🏥 Hospital Booking System - Tenant Tables Creator")
    print("=" * 55)
    
    # ถาม subdomain
    subdomain = input("Enter subdomain to create (e.g., 'demo'): ").strip()
    
    if not subdomain:
        print("❌ Subdomain is required")
        return
    
    # ตรวจสอบว่า subdomain ถูกต้องไหม
    if not subdomain.replace('-', '').isalnum():
        print("❌ Subdomain must contain only alphanumeric characters and hyphens")
        return
    
    try:
        create_tenant_tables(subdomain)
        print(f"\n✅ Success! You can now use:")
        print(f"   🌐 Web: http://localhost:5001/dashboard?subdomain={subdomain}")
        print(f"   🔗 API: http://localhost:8000/api/v1/tenants/{subdomain}/event-types")
        
    except Exception as e:
        print(f"\n❌ Failed to create tenant tables: {e}")
        return

if __name__ == "__main__":
    main()