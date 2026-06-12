# shared_db/seed.py
"""
สร้างข้อมูลเริ่มต้น (default setup) ใน tenant schema ใหม่
ใช้ร่วมกันทั้งเส้นทางสมัครผ่าน /api/register (FastAPI) และการสร้าง tenant จาก Super Admin panel

หลักการ: tenant ใหม่ต้อง "จองได้ทันที" โดยไม่ต้องตั้งค่าอะไรก่อน
และทุกอย่างที่ seed ไว้ผู้ใช้แก้ไข/ลบได้เองจากหน้า settings ภายหลัง
"""

from datetime import date, time

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models

DEFAULT_TEMPLATE_NAME = "เวลาทำการเริ่มต้น"

WORKING_DAYS = [
    models.DayOfWeek.MONDAY,
    models.DayOfWeek.TUESDAY,
    models.DayOfWeek.WEDNESDAY,
    models.DayOfWeek.THURSDAY,
    models.DayOfWeek.FRIDAY,
]

DEFAULT_EVENT_TYPES = [
    {
        'name': 'นัดหมายทั่วไป',
        'slug': 'general',
        'duration_minutes': 30,
        'color': '#6366f1',
        'description': 'นัดหมายรับบริการทั่วไป (แก้ไขชื่อและรายละเอียดได้ในหน้าตั้งค่า)',
    },
    {
        'name': 'ปรึกษา/ติดตามอาการ',
        'slug': 'follow-up',
        'duration_minutes': 15,
        'color': '#10b981',
        'description': 'นัดติดตามอาการหรือปรึกษาระยะสั้น',
    },
]


def seed_tenant_defaults(db: Session, schema_name: str):
    """สร้างข้อมูลเริ่มต้นใน tenant schema (idempotent — ถ้ามี template อยู่แล้วจะข้าม)

    สิ่งที่สร้าง:
      - AvailabilityTemplate "เวลาทำการเริ่มต้น" จันทร์-ศุกร์ 08:30-16:30
      - Availability 5 แถว (จ-ศ)
      - EventType 2 รายการ ผูกกับ template
      - Provider กลางๆ 1 คน ("เจ้าหน้าที่ให้บริการ") ผูกกับ template + ตารางเวลาทำงาน

    คืนค่า dict สรุปสิ่งที่สร้าง หรือ None ถ้า schema มีข้อมูลอยู่แล้ว (ไม่ seed ซ้ำ)
    """
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))

        # Idempotency: tenant ที่เคยตั้งค่าแล้วต้องไม่ถูกเขียนทับ
        if db.query(models.AvailabilityTemplate.id).first() is not None:
            return None

        template = models.AvailabilityTemplate(
            name=DEFAULT_TEMPLATE_NAME,
            description="จันทร์-ศุกร์ (08:30-16:30) — แก้ไขวันและเวลาได้ในหน้าตั้งค่า",
            timezone="Asia/Bangkok",
        )
        db.add(template)
        db.flush()

        for day in WORKING_DAYS:
            db.add(models.Availability(
                template_id=template.id,
                day_of_week=day,
                start_time=time(8, 30),
                end_time=time(16, 30),
            ))

        event_type_count = 0
        for data in DEFAULT_EVENT_TYPES:
            db.add(models.EventType(template_id=template.id, **data))
            event_type_count += 1

        provider = models.Provider(
            name="เจ้าหน้าที่ให้บริการ",
            department="ทั่วไป",
            bio="ผู้ให้บริการเริ่มต้นของระบบ — แก้ไขชื่อหรือเพิ่มเจ้าหน้าที่จริงได้ในหน้าตั้งค่า",
        )
        db.add(provider)
        db.flush()

        db.add(models.TemplateProvider(
            template_id=template.id,
            provider_id=provider.id,
            is_primary=True,
            can_auto_assign=True,
            priority=0,
        ))

        db.add(models.ProviderSchedule(
            provider_id=provider.id,
            template_id=template.id,
            effective_date=date.today(),
            end_date=None,
            days_of_week=[day.value for day in WORKING_DAYS],
            schedule_type='regular',
            notes='Default schedule created automatically',
        ))

        # เก็บค่าก่อน commit — หลัง commit attribute จะ expire และ refresh
        # อาจวิ่งไปคนละ connection ที่ search_path ไม่ใช่ tenant schema นี้แล้ว
        summary = {
            'template_id': template.id,
            'availabilities': len(WORKING_DAYS),
            'event_types': event_type_count,
            'providers': 1,
        }
        db.commit()
        return summary

    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.commit()
