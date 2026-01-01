#!/usr/bin/env python3
"""
Script to create a Super Admin user
This should be run after the database migration is complete
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared_db.database import SessionLocal
from shared_db.models import User, UserRole
from getpass import getpass
from dotenv import load_dotenv

# Load .env file from project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path)

def create_super_admin():
    """Create a super admin user interactively"""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("🏥 สร้าง Super Admin User")
        print("=" * 60)
        print("\nกรุณากรอกข้อมูล Super Admin:\n")

        # Get user input
        email = input("Email: ").strip()
        if not email:
            print("❌ Error: Email ต้องไม่เป็นค่าว่าง")
            return

        # Check if email already exists
        existing = db.query(User).filter_by(email=email).first()
        if existing:
            print(f"\n❌ Error: มี email {email} ในระบบแล้ว")
            if existing.role == UserRole.SUPER_ADMIN:
                print(f"   User นี้เป็น Super Admin อยู่แล้ว")
            else:
                print(f"   User นี้เป็น Hospital Admin (hospital_id: {existing.hospital_id})")
            return

        name = input("ชื่อ-นามสกุล: ").strip()
        if not name:
            print("❌ Error: ชื่อต้องไม่เป็นค่าว่าง")
            return

        phone = input("เบอร์โทรศัพท์ (optional, กด Enter เพื่อข้าม): ").strip()
        phone = phone if phone else None

        # Get password with confirmation
        while True:
            password = getpass("Password: ")
            if not password:
                print("❌ Error: Password ต้องไม่เป็นค่าว่าง")
                continue

            if len(password) < 6:
                print("❌ Error: Password ต้องมีอย่างน้อย 6 ตัวอักษร")
                continue

            confirm_password = getpass("ยืนยัน Password: ")
            if password != confirm_password:
                print("❌ Error: Password ไม่ตรงกัน กรุณาลองใหม่\n")
                continue

            break

        # Create super admin user
        user = User(
            email=email,
            name=name,
            phone_number=phone,
            role=UserRole.SUPER_ADMIN,
            hospital_id=None  # Super admin ไม่ผูกกับ hospital
        )
        user.set_password(password)

        db.add(user)
        db.commit()

        print("\n" + "=" * 60)
        print("✅ สร้าง Super Admin สำเร็จ!")
        print("=" * 60)
        print(f"📧 Email: {email}")
        print(f"👤 ชื่อ: {name}")
        if phone:
            print(f"📞 เบอร์: {phone}")
        print(f"🔑 Role: {user.role.value}")
        print("=" * 60)
        print("\nขั้นตอนต่อไป:")
        print("1. รัน admin app: python run_admin.py")
        print("2. เข้าสู่ระบบที่ http://localhost:5001")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n❌ ยกเลิกการสร้าง Super Admin")
        db.rollback()
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {str(e)}")
        raise
    finally:
        db.close()

def list_super_admins():
    """List all super admin users"""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("📋 รายการ Super Admin ทั้งหมด")
        print("=" * 60)

        super_admins = db.query(User).filter_by(role=UserRole.SUPER_ADMIN).all()

        if not super_admins:
            print("\n⚠️  ยังไม่มี Super Admin ในระบบ")
            print("   ใช้คำสั่ง: python scripts/create_super_admin.py")
            print("=" * 60)
            return

        print(f"\nพบ Super Admin จำนวน {len(super_admins)} คน:\n")

        for i, user in enumerate(super_admins, 1):
            print(f"{i}. {user.name}")
            print(f"   Email: {user.email}")
            if user.phone_number:
                print(f"   Phone: {user.phone_number}")
            if user.created_at:
                print(f"   Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_super_admins()
    else:
        create_super_admin()
