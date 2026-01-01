#!/usr/bin/env python3
"""
Migration: Add Tenant Management Features
- Add UserRole enum (super_admin, hospital_admin)
- Add HospitalStatus enum (active, inactive, deleted)
- Add role field to users table
- Make hospital_id nullable in users table
- Add status and additional fields to hospitals table
- Add timestamps to both tables
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def migrate():
    """Apply migration - เพิ่ม role, status fields และ timestamps"""
    db = Session()

    try:
        print("=" * 60)
        print("Starting Tenant Management Migration...")
        print("=" * 60)

        # 1. Create UserRole enum type
        print("\n[1/10] Creating UserRole enum type...")
        try:
            db.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE user_role AS ENUM ('super_admin', 'hospital_admin');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            db.commit()
            print("✓ UserRole enum created successfully")
        except Exception as e:
            print(f"⚠ UserRole enum might already exist: {e}")
            db.rollback()

        # 2. Create HospitalStatus enum type
        print("\n[2/10] Creating HospitalStatus enum type...")
        try:
            db.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE hospital_status AS ENUM ('active', 'inactive', 'deleted');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            db.commit()
            print("✓ HospitalStatus enum created successfully")
        except Exception as e:
            print(f"⚠ HospitalStatus enum might already exist: {e}")
            db.rollback()

        # 3. Add role field to users table
        print("\n[3/10] Adding role field to users table...")
        try:
            db.execute(text("""
                ALTER TABLE public.users
                ADD COLUMN IF NOT EXISTS role user_role DEFAULT 'hospital_admin' NOT NULL;
            """))
            db.commit()
            print("✓ Role field added to users table")
        except Exception as e:
            print(f"✗ Error adding role field: {e}")
            db.rollback()
            raise

        # 4. Make hospital_id nullable for super admins
        print("\n[4/10] Making hospital_id nullable in users table...")
        try:
            db.execute(text("""
                ALTER TABLE public.users
                ALTER COLUMN hospital_id DROP NOT NULL;
            """))
            db.commit()
            print("✓ hospital_id is now nullable")
        except Exception as e:
            print(f"✗ Error making hospital_id nullable: {e}")
            db.rollback()
            raise

        # 5. Add timestamps to users table
        print("\n[5/10] Adding timestamps to users table...")
        try:
            db.execute(text("""
                ALTER TABLE public.users
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW(),
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
            """))
            db.commit()
            print("✓ Timestamps added to users table")
        except Exception as e:
            print(f"✗ Error adding timestamps to users: {e}")
            db.rollback()
            raise

        # 6. Add status field to hospitals table
        print("\n[6/10] Adding status field to hospitals table...")
        try:
            db.execute(text("""
                ALTER TABLE public.hospitals
                ADD COLUMN IF NOT EXISTS status hospital_status DEFAULT 'active' NOT NULL;
            """))
            db.commit()
            print("✓ Status field added to hospitals table")
        except Exception as e:
            print(f"✗ Error adding status field: {e}")
            db.rollback()
            raise

        # 7. Add is_public_booking_enabled to hospitals table
        print("\n[7/10] Adding is_public_booking_enabled to hospitals table...")
        try:
            db.execute(text("""
                ALTER TABLE public.hospitals
                ADD COLUMN IF NOT EXISTS is_public_booking_enabled BOOLEAN DEFAULT TRUE;
            """))
            db.commit()
            print("✓ is_public_booking_enabled field added")
        except Exception as e:
            print(f"✗ Error adding is_public_booking_enabled: {e}")
            db.rollback()
            raise

        # 8. Add additional fields to hospitals table
        print("\n[8/10] Adding additional info fields to hospitals table...")
        try:
            db.execute(text("""
                ALTER TABLE public.hospitals
                ADD COLUMN IF NOT EXISTS address TEXT,
                ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
                ADD COLUMN IF NOT EXISTS email VARCHAR(120),
                ADD COLUMN IF NOT EXISTS description TEXT;
            """))
            db.commit()
            print("✓ Additional fields (address, phone, email, description) added")
        except Exception as e:
            print(f"✗ Error adding additional fields: {e}")
            db.rollback()
            raise

        # 9. Add timestamps to hospitals table
        print("\n[9/10] Adding timestamps to hospitals table...")
        try:
            db.execute(text("""
                ALTER TABLE public.hospitals
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW(),
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW(),
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
            """))
            db.commit()
            print("✓ Timestamps added to hospitals table")
        except Exception as e:
            print(f"✗ Error adding timestamps to hospitals: {e}")
            db.rollback()
            raise

        # 10. Update existing hospitals to active status
        print("\n[10/10] Updating existing hospitals to active status...")
        try:
            result = db.execute(text("""
                UPDATE public.hospitals
                SET status = 'active'
                WHERE status IS NULL;
            """))
            db.commit()
            rows_updated = result.rowcount
            print(f"✓ Updated {rows_updated} hospital(s) to active status")
        except Exception as e:
            print(f"✗ Error updating hospital status: {e}")
            db.rollback()
            raise

        print("\n" + "=" * 60)
        print("Migration completed successfully! ✓")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Run: python scripts/create_super_admin.py")
        print("2. Start admin app: python run_admin.py")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print("\n" + "=" * 60)
        print(f"Migration failed! ✗")
        print("=" * 60)
        print(f"\nError: {str(e)}")
        print("\nTo rollback, run:")
        print("  python migrations/add_tenant_management.py rollback")
        print("=" * 60)
        raise
    finally:
        db.close()

def rollback():
    """Rollback migration - ลบ fields และ enum types ที่เพิ่มเข้าไป"""
    db = Session()

    try:
        print("=" * 60)
        print("Rolling back Tenant Management Migration...")
        print("=" * 60)

        # 1. Remove fields from hospitals
        print("\n[1/5] Removing fields from hospitals table...")
        try:
            db.execute(text("""
                ALTER TABLE public.hospitals
                DROP COLUMN IF EXISTS status,
                DROP COLUMN IF EXISTS is_public_booking_enabled,
                DROP COLUMN IF EXISTS address,
                DROP COLUMN IF EXISTS phone,
                DROP COLUMN IF EXISTS email,
                DROP COLUMN IF EXISTS description,
                DROP COLUMN IF EXISTS created_at,
                DROP COLUMN IF EXISTS updated_at,
                DROP COLUMN IF EXISTS deleted_at;
            """))
            db.commit()
            print("✓ Fields removed from hospitals table")
        except Exception as e:
            print(f"✗ Error removing fields from hospitals: {e}")
            db.rollback()
            raise

        # 2. Remove fields from users
        print("\n[2/5] Removing fields from users table...")
        try:
            db.execute(text("""
                ALTER TABLE public.users
                DROP COLUMN IF EXISTS role,
                DROP COLUMN IF EXISTS created_at,
                DROP COLUMN IF EXISTS updated_at;
            """))
            db.commit()
            print("✓ Fields removed from users table")
        except Exception as e:
            print(f"✗ Error removing fields from users: {e}")
            db.rollback()
            raise

        # 3. Make hospital_id NOT NULL again (only if all users have hospital_id)
        print("\n[3/5] Making hospital_id NOT NULL again...")
        try:
            # Check if there are any users without hospital_id
            result = db.execute(text("""
                SELECT COUNT(*) FROM public.users WHERE hospital_id IS NULL;
            """))
            null_count = result.scalar()

            if null_count > 0:
                print(f"⚠ Warning: {null_count} user(s) have NULL hospital_id")
                print("  Cannot make hospital_id NOT NULL. Please delete super admins first.")
            else:
                db.execute(text("""
                    ALTER TABLE public.users
                    ALTER COLUMN hospital_id SET NOT NULL;
                """))
                db.commit()
                print("✓ hospital_id is now NOT NULL again")
        except Exception as e:
            print(f"✗ Error making hospital_id NOT NULL: {e}")
            db.rollback()
            raise

        # 4. Drop enum types
        print("\n[4/5] Dropping enum types...")
        try:
            db.execute(text("DROP TYPE IF EXISTS hospital_status;"))
            db.commit()
            print("✓ HospitalStatus enum dropped")
        except Exception as e:
            print(f"✗ Error dropping hospital_status enum: {e}")
            db.rollback()
            raise

        try:
            db.execute(text("DROP TYPE IF EXISTS user_role;"))
            db.commit()
            print("✓ UserRole enum dropped")
        except Exception as e:
            print(f"✗ Error dropping user_role enum: {e}")
            db.rollback()
            raise

        print("\n" + "=" * 60)
        print("Rollback completed successfully! ✓")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print("\n" + "=" * 60)
        print(f"Rollback failed! ✗")
        print("=" * 60)
        print(f"\nError: {str(e)}")
        print("=" * 60)
        raise
    finally:
        db.close()

def check_status():
    """Check current migration status"""
    db = Session()

    try:
        print("=" * 60)
        print("Checking Migration Status...")
        print("=" * 60)

        # Check if enum types exist
        print("\nEnum Types:")
        result = db.execute(text("""
            SELECT typname FROM pg_type
            WHERE typname IN ('user_role', 'hospital_status');
        """))
        enums = [row[0] for row in result]
        print(f"  user_role: {'✓ exists' if 'user_role' in enums else '✗ not found'}")
        print(f"  hospital_status: {'✓ exists' if 'hospital_status' in enums else '✗ not found'}")

        # Check users table columns
        print("\nUsers Table Columns:")
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
            AND column_name IN ('role', 'created_at', 'updated_at', 'hospital_id');
        """))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")

        # Check hospitals table columns
        print("\nHospitals Table Columns:")
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'hospitals'
            AND column_name IN ('status', 'is_public_booking_enabled', 'address', 'phone',
                              'email', 'description', 'created_at', 'updated_at', 'deleted_at');
        """))
        for row in result:
            print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")

        # Count super admins
        print("\nUser Statistics:")
        result = db.execute(text("""
            SELECT role, COUNT(*)
            FROM public.users
            GROUP BY role;
        """))
        for row in result:
            if row[0]:
                print(f"  {row[0]}: {row[1]} user(s)")

        # Count hospitals by status
        print("\nHospital Statistics:")
        result = db.execute(text("""
            SELECT status, COUNT(*)
            FROM public.hospitals
            GROUP BY status;
        """))
        for row in result:
            if row[0]:
                print(f"  {row[0]}: {row[1]} hospital(s)")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"\nError checking status: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "rollback":
            rollback()
        elif command == "status":
            check_status()
        else:
            print("Unknown command. Use: migrate (default), rollback, or status")
    else:
        migrate()
