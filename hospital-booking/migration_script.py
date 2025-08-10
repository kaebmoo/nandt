# migration_script.py - แก้ไข Database Schema ที่มีอยู่

import os
import sys
sys.path.append('flask_app/app')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import models

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_existing_tenants():
    """ดึงรายการ tenant ที่มีอยู่"""
    db = SessionLocal()
    try:
        db.execute(text("SET search_path TO public"))
        result = db.execute(text("SELECT subdomain, schema_name FROM hospitals")).fetchall()
        return result
    finally:
        db.close()

def check_table_structure(schema_name, table_name):
    """ตรวจสอบ structure ของ table"""
    db = SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        result = db.execute(text(f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            AND table_schema = '{schema_name}'
            ORDER BY ordinal_position;
        """)).fetchall()
        return result
    except Exception as e:
        print(f"Error checking table {table_name} in schema {schema_name}: {e}")
        return []
    finally:
        db.close()

def migrate_tenant_schema(schema_name):
    """อัปเดต schema ของ tenant"""
    db = SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        print(f"\n🔄 Migrating schema: {schema_name}")
        
        # ตรวจสอบ table ที่มีอยู่
        existing_tables = db.execute(text(f"""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = '{schema_name}';
        """)).fetchall()
        
        existing_table_names = [row[0] for row in existing_tables]
        print(f"📋 Existing tables: {existing_table_names}")
        
        # 1. สร้าง tables ใหม่ที่ยังไม่มี
        required_tables = [
            'event_types', 'service_types', 'providers', 
            'availabilities', 'date_overrides', 'holidays'
        ]
        
        for table_name in required_tables:
            if table_name not in existing_table_names:
                print(f"➕ Creating table: {table_name}")
                if table_name == 'event_types':
                    create_event_types_table(db, schema_name)
                elif table_name == 'service_types':
                    create_service_types_table(db, schema_name)
                elif table_name == 'providers':
                    create_providers_table(db, schema_name)
                elif table_name == 'availabilities':
                    create_availabilities_table(db, schema_name)
                elif table_name == 'date_overrides':
                    create_date_overrides_table(db, schema_name)
                elif table_name == 'holidays':
                    create_holidays_table(db, schema_name)
        
        # 2. อัปเดต appointments table
        if 'appointments' in existing_table_names:
            print("🔧 Updating appointments table...")
            update_appointments_table(db, schema_name)
        else:
            print("➕ Creating appointments table...")
            create_appointments_table(db, schema_name)
        
        # 3. อัปเดต patients table
        if 'patients' in existing_table_names:
            print("🔧 Updating patients table...")
            update_patients_table(db, schema_name)
        
        # 4. เพิ่มข้อมูลเริ่มต้น
        print("🌱 Adding default data...")
        add_default_data(db, schema_name)
        
        db.commit()
        print(f"✅ Migration completed for {schema_name}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed for {schema_name}: {e}")
        raise
    finally:
        db.close()

def create_event_types_table(db, schema_name):
    """สร้าง event_types table"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".event_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(50) NOT NULL UNIQUE,
            description TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 15,
            color VARCHAR(7) DEFAULT '#6366f1',
            is_active BOOLEAN DEFAULT TRUE,
            buffer_before_minutes INTEGER DEFAULT 0,
            buffer_after_minutes INTEGER DEFAULT 0,
            max_bookings_per_day INTEGER,
            min_notice_hours INTEGER DEFAULT 4,
            max_advance_days INTEGER DEFAULT 60,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

def create_service_types_table(db, schema_name):
    """สร้าง service_types table"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".service_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE
        );
    """))

def create_providers_table(db, schema_name):
    """สร้าง providers table"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".providers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            title VARCHAR(50),
            department VARCHAR(100),
            email VARCHAR(120),
            phone VARCHAR(20),
            is_active BOOLEAN DEFAULT TRUE,
            public_booking_url VARCHAR(100) UNIQUE,
            bio TEXT,
            profile_image_url VARCHAR(255)
        );
    """))

def create_availabilities_table(db, schema_name):
    """สร้าง availabilities table"""
    db.execute(text(f"""
        CREATE TYPE "{schema_name}".day_of_week AS ENUM ('0', '1', '2', '3', '4', '5', '6');
        
        CREATE TABLE "{schema_name}".availabilities (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES "{schema_name}".providers(id),
            event_type_id INTEGER NOT NULL REFERENCES "{schema_name}".event_types(id),
            day_of_week "{schema_name}".day_of_week NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            timezone VARCHAR(50) DEFAULT 'Asia/Bangkok',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

def create_date_overrides_table(db, schema_name):
    """สร้าง date_overrides table"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".date_overrides (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES "{schema_name}".providers(id),
            date DATE NOT NULL,
            is_unavailable BOOLEAN DEFAULT FALSE,
            custom_start_time TIME,
            custom_end_time TIME,
            reason VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

def create_holidays_table(db, schema_name):
    """สร้าง holidays table"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".holidays (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            date DATE NOT NULL,
            is_recurring BOOLEAN DEFAULT FALSE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

def update_appointments_table(db, schema_name):
    """อัปเดต appointments table"""
    # ตรวจสอบ columns ที่มีอยู่
    columns = check_table_structure(schema_name, 'appointments')
    existing_columns = [col[0] for col in columns]
    
    # เพิ่ม columns ที่ขาดหายไป
    new_columns = [
        ('provider_id', 'INTEGER'),
        ('event_type_id', 'INTEGER'),
        ('service_type_id', 'INTEGER'),
        ('booking_reference', 'VARCHAR(20) UNIQUE'),
        ('status', 'VARCHAR(20) DEFAULT \'confirmed\''),
        ('guest_name', 'VARCHAR(100)'),
        ('guest_email', 'VARCHAR(120)'),
        ('guest_phone', 'VARCHAR(20)'),
        ('internal_notes', 'TEXT'),
        ('reminder_sent', 'BOOLEAN DEFAULT FALSE'),
        ('reminder_sent_at', 'TIMESTAMP'),
        ('cancelled_at', 'TIMESTAMP'),
        ('cancelled_by', 'VARCHAR(50)'),
        ('cancellation_reason', 'TEXT'),
        ('rescheduled_from_id', 'INTEGER'),
        ('reschedule_count', 'INTEGER DEFAULT 0'),
        ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ]
    
    for column_name, column_type in new_columns:
        if column_name not in existing_columns:
            print(f"  ➕ Adding column: {column_name}")
            db.execute(text(f"""
                ALTER TABLE "{schema_name}".appointments 
                ADD COLUMN {column_name} {column_type};
            """))
    
    # เพิ่ม foreign keys (ถ้ายังไม่มี)
    try:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".appointments 
            ADD CONSTRAINT fk_appointments_provider 
            FOREIGN KEY (provider_id) REFERENCES "{schema_name}".providers(id);
        """))
    except:
        pass  # FK อาจมีอยู่แล้ว
    
    try:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".appointments 
            ADD CONSTRAINT fk_appointments_event_type 
            FOREIGN KEY (event_type_id) REFERENCES "{schema_name}".event_types(id);
        """))
    except:
        pass
    
    try:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".appointments 
            ADD CONSTRAINT fk_appointments_service_type 
            FOREIGN KEY (service_type_id) REFERENCES "{schema_name}".service_types(id);
        """))
    except:
        pass

def create_appointments_table(db, schema_name):
    """สร้าง appointments table ใหม่"""
    db.execute(text(f"""
        CREATE TABLE "{schema_name}".appointments (
            id SERIAL PRIMARY KEY,
            patient_id INTEGER REFERENCES "{schema_name}".patients(id),
            provider_id INTEGER REFERENCES "{schema_name}".providers(id),
            event_type_id INTEGER REFERENCES "{schema_name}".event_types(id),
            service_type_id INTEGER REFERENCES "{schema_name}".service_types(id),
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            booking_reference VARCHAR(20) UNIQUE,
            status VARCHAR(20) DEFAULT 'confirmed',
            guest_name VARCHAR(100),
            guest_email VARCHAR(120),
            guest_phone VARCHAR(20),
            notes VARCHAR(500),
            internal_notes TEXT,
            reminder_sent BOOLEAN DEFAULT FALSE,
            reminder_sent_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            cancelled_by VARCHAR(50),
            cancellation_reason TEXT,
            rescheduled_from_id INTEGER REFERENCES "{schema_name}".appointments(id),
            reschedule_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

def update_patients_table(db, schema_name):
    """อัปเดต patients table"""
    columns = check_table_structure(schema_name, 'patients')
    existing_columns = [col[0] for col in columns]
    
    new_columns = [
        ('date_of_birth', 'DATE'),
        ('national_id', 'VARCHAR(20)'),
        ('address', 'TEXT'),
        ('emergency_contact', 'VARCHAR(100)'),
        ('emergency_phone', 'VARCHAR(20)'),
        ('allergies', 'TEXT'),
        ('medical_conditions', 'TEXT'),
        ('current_medications', 'TEXT'),
        ('preferred_language', 'VARCHAR(10) DEFAULT \'th\''),
        ('communication_preference', 'VARCHAR(20) DEFAULT \'sms\''),
        ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ]
    
    for column_name, column_type in new_columns:
        if column_name not in existing_columns:
            print(f"  ➕ Adding column to patients: {column_name}")
            db.execute(text(f"""
                ALTER TABLE "{schema_name}".patients 
                ADD COLUMN {column_name} {column_type};
            """))

def add_default_data(db, schema_name):
    """เพิ่มข้อมูลเริ่มต้น"""
    
    # Event Types
    db.execute(text(f"""
        INSERT INTO "{schema_name}".event_types (name, slug, description, duration_minutes, color)
        VALUES 
        ('15 Min Meeting', '15min', 'การนัดหมายสั้น 15 นาที', 15, '#6366f1'),
        ('30 Min Consultation', '30min', 'การปรึกษา 30 นาที', 30, '#059669'),
        ('Health Screening', 'screening', 'ตรวจสุขภาพทั่วไป', 60, '#dc2626')
        ON CONFLICT (slug) DO NOTHING;
    """))
    
    # Service Types
    db.execute(text(f"""
        INSERT INTO "{schema_name}".service_types (name, description)
        VALUES 
        ('general', 'ตรวจรักษาทั่วไป'),
        ('vaccination', 'ฉีดวัคซีน'),
        ('screening', 'ตรวจสุขภาพ'),
        ('consultation', 'ปรึกษาปัญหาสุขภาพ')
        ON CONFLICT DO NOTHING;
    """))
    
    # Provider (ตัวอย่าง)
    db.execute(text(f"""
        INSERT INTO "{schema_name}".providers (name, title, department, public_booking_url, bio)
        VALUES 
        ('สมชาย ใจดี', 'นพ.', 'เวชศาสตร์ครอบครัว', 'dr-somchai', 'แพทย์เวชศาสตร์ครอบครัวที่มีประสบการณ์กว่า 10 ปี')
        ON CONFLICT (public_booking_url) DO NOTHING;
    """))

def main():
    """รัน migration หลัก"""
    print("🚀 Starting database migration...")
    
    # ดึงรายการ tenant ที่มีอยู่
    tenants = get_existing_tenants()
    print(f"📋 Found {len(tenants)} tenants: {[t[0] for t in tenants]}")
    
    for subdomain, schema_name in tenants:
        try:
            migrate_tenant_schema(schema_name)
        except Exception as e:
            print(f"❌ Failed to migrate {schema_name}: {e}")
            continue
    
    print("\n🎉 Migration completed!")
    print("\n⚠️  Please restart your Flask application")

if __name__ == "__main__":
    main()