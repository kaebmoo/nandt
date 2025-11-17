#!/usr/bin/env python3
"""
Migration: เพิ่มตารางสำหรับ Availability Templates System
Date: 2025-11-17
Purpose: สร้างตาราง availability_templates, template_providers, provider_schedules,
         resource_capacities, provider_leaves
"""

import os
import sys
from pathlib import Path

# เพิ่ม path สำหรับ import
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    sys.exit(1)

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


def create_availability_templates_table(db, schema_name):
    """สร้างตาราง availability_templates"""
    print(f"  📝 Creating availability_templates table...")
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}".availability_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            template_type VARCHAR(20) DEFAULT 'dedicated',
            max_concurrent_slots INTEGER DEFAULT 1,
            requires_provider_assignment BOOLEAN DEFAULT TRUE,
            timezone VARCHAR(50) DEFAULT 'Asia/Bangkok',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))


def create_availabilities_with_template_table(db, schema_name):
    """อัปเดตตาราง availabilities ให้รองรับ template_id"""
    print(f"  📝 Updating availabilities table...")

    # เช็คว่ามีคอลัมน์ template_id หรือยัง
    result = db.execute(text(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
        AND table_name = 'availabilities'
        AND column_name = 'template_id';
    """)).fetchone()

    if not result:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".availabilities
            ADD COLUMN template_id INTEGER REFERENCES "{schema_name}".availability_templates(id);
        """))
        print(f"    ✅ Added template_id column")


def create_template_providers_table(db, schema_name):
    """สร้างตาราง template_providers"""
    print(f"  📝 Creating template_providers table...")
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}".template_providers (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES "{schema_name}".availability_templates(id) ON DELETE CASCADE,
            provider_id INTEGER NOT NULL REFERENCES "{schema_name}".providers(id) ON DELETE CASCADE,
            is_primary BOOLEAN DEFAULT FALSE,
            can_auto_assign BOOLEAN DEFAULT TRUE,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(template_id, provider_id)
        );
    """))


def create_provider_schedules_table(db, schema_name):
    """สร้างตาราง provider_schedules"""
    print(f"  📝 Creating provider_schedules table...")
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}".provider_schedules (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES "{schema_name}".availability_templates(id) ON DELETE CASCADE,
            provider_id INTEGER NOT NULL REFERENCES "{schema_name}".providers(id) ON DELETE CASCADE,
            effective_date DATE NOT NULL,
            end_date DATE,
            days_of_week INTEGER[] NOT NULL,
            custom_start_time TIME,
            custom_end_time TIME,
            schedule_type VARCHAR(20) DEFAULT 'regular',
            recurrence_pattern VARCHAR(50),
            notes TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))


def create_resource_capacities_table(db, schema_name):
    """สร้างตาราง resource_capacities"""
    print(f"  📝 Creating resource_capacities table...")
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}".resource_capacities (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES "{schema_name}".availability_templates(id) ON DELETE CASCADE,
            specific_date DATE,
            day_of_week INTEGER CHECK (day_of_week >= 0 AND day_of_week <= 6),
            time_slot_start TIME,
            time_slot_end TIME,
            available_rooms INTEGER NOT NULL,
            max_concurrent_appointments INTEGER,
            notes TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (specific_date IS NOT NULL OR day_of_week IS NOT NULL)
        );
    """))


def create_provider_leaves_table(db, schema_name):
    """สร้างตาราง provider_leaves"""
    print(f"  📝 Creating provider_leaves table...")
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}".provider_leaves (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES "{schema_name}".providers(id) ON DELETE CASCADE,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            leave_type VARCHAR(50),
            reason TEXT,
            approved_by VARCHAR(100),
            is_approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (end_date >= start_date)
        );
    """))


def update_event_types_table(db, schema_name):
    """อัปเดต event_types ให้รองรับ template_id"""
    print(f"  📝 Updating event_types table...")

    # เช็คว่ามีคอลัมน์ template_id หรือยัง
    result = db.execute(text(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
        AND table_name = 'event_types'
        AND column_name = 'template_id';
    """)).fetchone()

    if not result:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".event_types
            ADD COLUMN template_id INTEGER REFERENCES "{schema_name}".availability_templates(id);
        """))
        print(f"    ✅ Added template_id column to event_types")


def update_date_overrides_table(db, schema_name):
    """อัปเดต date_overrides ให้รองรับ template_id"""
    print(f"  📝 Updating date_overrides table...")

    # เช็คว่ามีคอลัมน์ template_id หรือยัง
    result = db.execute(text(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
        AND table_name = 'date_overrides'
        AND column_name = 'template_id';
    """)).fetchone()

    if not result:
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".date_overrides
            ADD COLUMN template_id INTEGER REFERENCES "{schema_name}".availability_templates(id),
            ADD COLUMN template_scope VARCHAR(20) DEFAULT 'template';
        """))

        # ทำให้ provider_id เป็น nullable
        db.execute(text(f"""
            ALTER TABLE "{schema_name}".date_overrides
            ALTER COLUMN provider_id DROP NOT NULL;
        """))
        print(f"    ✅ Added template_id and template_scope columns")


def create_indexes(db, schema_name):
    """สร้าง indexes สำหรับ performance"""
    print(f"  📝 Creating indexes...")

    indexes = [
        f'CREATE INDEX IF NOT EXISTS idx_template_providers_template ON "{schema_name}".template_providers(template_id)',
        f'CREATE INDEX IF NOT EXISTS idx_template_providers_provider ON "{schema_name}".template_providers(provider_id)',
        f'CREATE INDEX IF NOT EXISTS idx_provider_schedules_template ON "{schema_name}".provider_schedules(template_id)',
        f'CREATE INDEX IF NOT EXISTS idx_provider_schedules_provider ON "{schema_name}".provider_schedules(provider_id)',
        f'CREATE INDEX IF NOT EXISTS idx_provider_schedules_dates ON "{schema_name}".provider_schedules(effective_date, end_date)',
        f'CREATE INDEX IF NOT EXISTS idx_resource_capacities_template ON "{schema_name}".resource_capacities(template_id)',
        f'CREATE INDEX IF NOT EXISTS idx_provider_leaves_provider ON "{schema_name}".provider_leaves(provider_id)',
        f'CREATE INDEX IF NOT EXISTS idx_provider_leaves_dates ON "{schema_name}".provider_leaves(start_date, end_date)',
    ]

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
        except Exception as e:
            print(f"    ⚠️  Index creation warning: {e}")


def migrate_tenant_schema(schema_name):
    """Migrate schema สำหรับ tenant"""
    db = SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))

        print(f"\n🔄 Migrating schema: {schema_name}")

        # 1. สร้าง availability_templates table
        create_availability_templates_table(db, schema_name)

        # 2. อัปเดต availabilities table
        create_availabilities_with_template_table(db, schema_name)

        # 3. สร้าง template_providers table
        create_template_providers_table(db, schema_name)

        # 4. สร้าง provider_schedules table
        create_provider_schedules_table(db, schema_name)

        # 5. สร้าง resource_capacities table
        create_resource_capacities_table(db, schema_name)

        # 6. สร้าง provider_leaves table
        create_provider_leaves_table(db, schema_name)

        # 7. อัปเดต event_types table
        update_event_types_table(db, schema_name)

        # 8. อัปเดต date_overrides table
        update_date_overrides_table(db, schema_name)

        # 9. สร้าง indexes
        create_indexes(db, schema_name)

        db.commit()
        print(f"✅ Migration completed for {schema_name}")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed for {schema_name}: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


def main():
    """รัน migration หลัก"""
    print("=" * 70)
    print("🚀 Starting Availability Templates Migration")
    print("=" * 70)

    # ดึงรายการ tenant ที่มีอยู่
    tenants = get_existing_tenants()
    print(f"\n📋 Found {len(tenants)} tenants: {[t[0] for t in tenants]}")

    success_count = 0
    failed_count = 0

    for subdomain, schema_name in tenants:
        try:
            migrate_tenant_schema(schema_name)
            success_count += 1
        except Exception as e:
            print(f"\n❌ Failed to migrate {schema_name}")
            failed_count += 1
            continue

    print("\n" + "=" * 70)
    print(f"🎉 Migration Summary:")
    print(f"  ✅ Success: {success_count} tenants")
    if failed_count > 0:
        print(f"  ❌ Failed: {failed_count} tenants")
    print("=" * 70)

    if success_count > 0:
        print("\n⚠️  Please restart your Flask/FastAPI application")


if __name__ == "__main__":
    main()
