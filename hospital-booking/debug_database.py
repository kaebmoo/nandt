# debug_database.py - Script สำหรับตรวจสอบและแก้ไขปัญหา Database

import os
import sys
from sqlalchemy import create_engine, text, inspect
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

def check_database_status():
    """ตรวจสอบสถานะ database และ schemas"""
    
    print("=== Database Status Check ===")
    
    db = SessionLocal()
    inspector = inspect(engine)
    
    try:
        # 1. ตรวจสอบ schemas ทั้งหมด
        print("\n📂 Available Schemas:")
        schemas = inspector.get_schema_names()
        for schema in schemas:
            print(f"   - {schema}")
        
        # 2. ตรวจสอบ tables ใน public schema
        print(f"\n📋 Tables in 'public' schema:")
        public_tables = inspector.get_table_names(schema='public')
        for table in public_tables:
            print(f"   - {table}")
        
        # 3. ตรวจสอบข้อมูลโรงพยาบาล
        print(f"\n🏥 Hospitals in database:")
        hospitals = db.query(models.Hospital).all()
        
        if not hospitals:
            print("   ❌ No hospitals found!")
            return False
            
        for hospital in hospitals:
            print(f"   - {hospital.name} (subdomain: {hospital.subdomain}, schema: {hospital.schema_name})")
            
            # ตรวจสอบว่า schema นี้มีอยู่จริงไหม
            if hospital.schema_name in schemas:
                print(f"     ✅ Schema '{hospital.schema_name}' exists")
                
                # ตรวจสอบ tables ใน schema นี้
                tenant_tables = inspector.get_table_names(schema=hospital.schema_name)
                if tenant_tables:
                    print(f"     📋 Tables: {', '.join(tenant_tables)}")
                else:
                    print(f"     ❌ No tables in schema '{hospital.schema_name}'")
                    return False
            else:
                print(f"     ❌ Schema '{hospital.schema_name}' does NOT exist")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False
    finally:
        db.close()

def fix_missing_tables():
    """แก้ไขปัญหา tables ที่หายไป"""
    
    print("\n=== Fixing Missing Tables ===")
    
    db = SessionLocal()
    
    try:
        hospitals = db.query(models.Hospital).all()
        
        for hospital in hospitals:
            schema_name = hospital.schema_name
            print(f"\n🔧 Fixing schema: {schema_name}")
            
            # สร้าง schema ถ้ายังไม่มี
            db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            print(f"   ✅ Schema created/verified")
            
            # สร้าง tables
            tenant_tables = [models.Patient.__table__, models.Appointment.__table__]
            
            # เก็บ schema เดิม
            original_schema = models.Base.metadata.schema
            
            try:
                # ตั้งค่า schema ใหม่
                models.Base.metadata.schema = schema_name
                
                for table in tenant_tables:
                    # สร้าง table ใน schema นี้
                    table_copy = table.tometadata(models.Base.metadata, schema=schema_name)
                    table_copy.create(db.bind, checkfirst=True)
                    print(f"   ✅ Table '{table.name}' created")
                    
            finally:
                # คืนค่า schema เดิม
                models.Base.metadata.schema = original_schema
        
        db.commit()
        print("\n✅ All schemas and tables fixed!")
        
    except Exception as e:
        print(f"❌ Error fixing tables: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def test_tenant_connection(subdomain):
    """ทดสอบการเชื่อมต่อกับ tenant schema"""
    
    print(f"\n=== Testing Tenant Connection: {subdomain} ===")
    
    db = SessionLocal()
    
    try:
        # หา hospital จาก subdomain
        hospital = db.query(models.Hospital).filter_by(subdomain=subdomain).first()
        
        if not hospital:
            print(f"❌ Hospital with subdomain '{subdomain}' not found")
            return False
            
        schema_name = hospital.schema_name
        print(f"🏥 Hospital: {hospital.name}")
        print(f"📂 Schema: {schema_name}")
        
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # ทดสอบ query
        result = db.execute(text("SELECT COUNT(*) FROM patients")).scalar()
        print(f"👥 Patients count: {result}")
        
        result = db.execute(text("SELECT COUNT(*) FROM appointments")).scalar()
        print(f"📅 Appointments count: {result}")
        
        print("✅ Tenant connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing tenant connection: {e}")
        return False
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

def create_sample_data(subdomain):
    """สร้างข้อมูลตัวอย่างสำหรับทดสอบ"""
    
    print(f"\n=== Creating Sample Data for: {subdomain} ===")
    
    db = SessionLocal()
    
    try:
        # หา hospital
        hospital = db.query(models.Hospital).filter_by(subdomain=subdomain).first()
        if not hospital:
            print(f"❌ Hospital '{subdomain}' not found")
            return
            
        schema_name = hospital.schema_name
        
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # สร้างผู้ป่วยตัวอย่าง
        sample_patients = [
            "INSERT INTO patients (name, phone_number, email) VALUES ('สมชาย ใจดี', '0812345678', 'somchai@email.com') ON CONFLICT DO NOTHING",
            "INSERT INTO patients (name, phone_number, email) VALUES ('สมหญิง สวยงาม', '0823456789', 'somying@email.com') ON CONFLICT DO NOTHING",
            "INSERT INTO patients (name, phone_number, email) VALUES ('สมศักดิ์ รักดี', '0834567890', 'somsak@email.com') ON CONFLICT DO NOTHING"
        ]
        
        for sql in sample_patients:
            db.execute(text(sql))
            
        # สร้างนัดหมายตัวอย่าง
        sample_appointments = [
            "INSERT INTO appointments (patient_id, start_time, end_time, notes) VALUES (1, '2024-08-11 09:00:00', '2024-08-11 09:30:00', 'ตรวจสุขภาพประจำปี') ON CONFLICT DO NOTHING",
            "INSERT INTO appointments (patient_id, start_time, end_time, notes) VALUES (2, '2024-08-11 10:00:00', '2024-08-11 10:30:00', 'รักษาฟัน') ON CONFLICT DO NOTHING",
            "INSERT INTO appointments (patient_id, start_time, end_time, notes) VALUES (3, '2024-08-11 14:00:00', '2024-08-11 14:30:00', 'ติดตามผล') ON CONFLICT DO NOTHING"
        ]
        
        for sql in sample_appointments:
            db.execute(text(sql))
            
        db.commit()
        print("✅ Sample data created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating sample data: {e}")
        db.rollback()
    finally:
        db.execute(text('SET search_path TO public'))
        db.close()

def main():
    """ฟังก์ชันหลักสำหรับรัน debug script"""
    
    print("🔍 Hospital Booking System - Database Debug Tool")
    print("=" * 50)
    
    # 1. ตรวจสอบสถานะ database
    if not check_database_status():
        print("\n❌ Database has issues. Attempting to fix...")
        fix_missing_tables()
        
        # ตรวจสอบอีกครั้ง
        if check_database_status():
            print("\n✅ Database issues resolved!")
        else:
            print("\n❌ Unable to resolve database issues.")
            return
    
    # 2. ทดสอบ tenant connection
    test_subdomain = "humnoi"  # เปลี่ยนเป็น subdomain ที่ต้องการทดสอบ
    
    if test_tenant_connection(test_subdomain):
        # 3. สร้างข้อมูลตัวอย่าง (ถ้าต้องการ)
        create_data = input(f"\n❓ Create sample data for '{test_subdomain}'? (y/N): ")
        if create_data.lower() == 'y':
            create_sample_data(test_subdomain)
    
    print(f"\n✅ Debug complete!")
    print(f"🌐 Try accessing: http://localhost:5001/dashboard?subdomain={test_subdomain}")

if __name__ == "__main__":
    main()