"""Unit tests สำหรับ delete-template edge case (Phase 1B P1-round4):
ลบ "default template" (เวลาทำการเริ่มต้น) เองที่มี event_types ผูกอยู่ → event_types ต้องย้ายไป
default ใหม่ ไม่หลุดเป็น template_id=NULL (ไม่งั้น booking reject "ยังไม่ได้ตั้งค่าเวลาทำการ")

ครอบ get_or_create_default_template(exclude_template_id=...) + การ replicate logic ลบ default
"""

from shared_db import models
from fastapi_app.app.availability import get_or_create_default_template

DEFAULT_NAME = "เวลาทำการเริ่มต้น"


def _default_template(db):
    t = models.AvailabilityTemplate(name=DEFAULT_NAME, is_active=True)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_get_or_create_excludes_template_being_deleted(db):
    """exclude id ของ default ที่กำลังจะลบ → ต้องไม่คืน id เดิม แต่สร้างใหม่"""
    t1 = _default_template(db)

    new_id = get_or_create_default_template(db, commit=False, exclude_template_id=t1.id)
    db.commit()

    assert new_id != t1.id
    new_t = db.query(models.AvailabilityTemplate).filter_by(id=new_id).one()
    assert new_t.name == DEFAULT_NAME and new_t.is_active is True


def test_get_or_create_returns_existing_when_not_excluded(db):
    t1 = _default_template(db)
    assert get_or_create_default_template(db, exclude_template_id=None) == t1.id


def test_delete_default_template_with_events_moves_to_new_default(db):
    """ลบ default template ที่มี event_types → event ย้ายไป default ใหม่ ไม่เป็น NULL (atomic, 1 commit)"""
    t1 = _default_template(db)
    et = models.EventType(name="svc", slug="svc-del-default", duration_minutes=30, template_id=t1.id)
    db.add(et)
    db.commit()
    db.refresh(et)

    # replicate delete_availability_template (event_types branch) — atomic, exclude ตัวที่ลบ
    events = db.query(models.EventType).filter_by(template_id=t1.id).all()
    default_id = get_or_create_default_template(db, commit=False, exclude_template_id=t1.id)
    default_tpl = db.query(models.AvailabilityTemplate).filter_by(id=default_id).one()
    for e in events:
        e.availability_template = default_tpl          # assign relationship (sync FK + ออกจาก collection)
    db.delete(db.query(models.AvailabilityTemplate).filter_by(id=t1.id).one())
    db.commit()                                        # atomic commit เดียว

    et2 = db.query(models.EventType).filter_by(id=et.id).one()
    assert et2.template_id is not None                 # ไม่หลุดเป็น NULL
    assert et2.template_id == default_id != t1.id       # ย้ายไป default ใหม่
    assert db.query(models.AvailabilityTemplate).filter_by(id=t1.id).one_or_none() is None  # ลบจริง
