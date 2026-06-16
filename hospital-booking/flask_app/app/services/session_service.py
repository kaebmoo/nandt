"""
Session generator — materialize `sessions` จาก availability template (แผน §5.8, Phase 1B)

"session" = การ materialize availability (template + date_overrides) ให้เป็นแถวจริง
ต่อวันต่อ service_point เพื่อให้ queue_entries ผูกกับ session ได้ และมี queue state คงที่

ที่มาของเวลาทำการ: service_points.availability_template_id → availability_templates(id)
(1B.0). generator อ่าน weekly `availabilities` ของ template นั้น (รองรับหลายบล็อก/วัน เช่น
จันทร์ 08:30-16:30 + 17:00-20:00 → 2 session) แล้ว apply `date_overrides` (per-template) ทับ

**ใช้ semantics เดียวกับ booking engine จริง** (fastapi_app/app/booking.py) เพื่อไม่ให้คิว
กับการจองตีความเวลาทำการต่างกัน:
- override resolution: template-specific ก่อน แล้ว fallback ไป global
  (= get_relevant_date_override)
- is_unavailable = ปิดทั้งวัน
- custom_start/custom_end = **REPLACE** ตารางปกติของวันนั้นทั้งหมดด้วยช่วง custom
  (ตรงกับ booking.py:628-633 ที่ทำ `base_slots = generate_time_slots(custom_start, custom_end, ...)`)
  → รองรับ "วันทำงานพิเศษ": เปิดวันที่ปกติปิดได้ (weekly ว่าง + custom hours → ยังได้ session)
- weekday mapping: Python date.weekday() (Mon=0..Sun=6) → DayOfWeek (Sun=0..Sat=6)
  (= convert_python_weekday)

กฎที่ต้องรักษา (แผน §5.8):
- Idempotent: UPSERT บน UNIQUE(service_point_id, session_date, name) เท่านั้น รันซ้ำไม่เกิดแถวซ้ำ
- History preservation: session ที่มี queue_entries แล้ว ห้ามแก้/ลบ (1B.4)
- ไม่ commit ทันทีหลัง SET search_path; commit ที่ท้ายงาน (g.db ผูก tenant โดย middleware แล้ว)

หมายเหตุ session.name: ใช้รูปแบบ "HH:MM-HH:MM" ของบล็อกเป็นชื่อ (stable + unique ต่อบล็อก)
จึงรองรับ multi-block และทำให้ idempotent (ชื่อไม่เปลี่ยนถ้าเวลาไม่เปลี่ยน)
"""

import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from shared_db import models
from shared_db.database import SessionLocal, bind_tenant

BANGKOK = ZoneInfo("Asia/Bangkok")


def today() -> datetime.date:
    """วันที่ "วันนี้" ตามเวลาไทย — generator sync เฉพาะอนาคต [today, ...]"""
    return datetime.datetime.now(BANGKOK).date()


def _dow_value(d: datetime.date) -> int:
    """Python weekday (Mon=0..Sun=6) → DayOfWeek enum value (Sun=0,Mon=1..Sat=6).

    ตรงกับ booking.convert_python_weekday — ห้ามแก้ให้ต่างจาก booking
    """
    py = d.weekday()
    return 0 if py == 6 else py + 1


def _relevant_override(db, template_id, target_date):
    """หา date_override ที่ effective ของวันนั้น — template-specific ก่อน แล้ว global
    (mirror fastapi_app/app/booking.py get_relevant_date_override)"""
    if template_id is not None:
        ov = (db.query(models.DateOverride)
              .filter(models.DateOverride.date == target_date,
                      models.DateOverride.template_id == template_id)
              .order_by(models.DateOverride.id.desc())
              .first())
        if ov:
            return ov
    return (db.query(models.DateOverride)
            .filter(models.DateOverride.date == target_date,
                    models.DateOverride.template_scope == 'global')
            .order_by(models.DateOverride.id.desc())
            .first())


def _session_name(start: datetime.time, end: datetime.time) -> str:
    """ชื่อ session ที่ stable + unique ต่อบล็อกเวลา (รองรับ multi-block + idempotent)"""
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _desired_blocks_for_date(weekly_by_dow, db, template_id, target_date):
    """คืน dict {name: (start, end)} ของ session ที่ "ควรมี" ในวันนั้น หลัง apply override

    semantics ตรงกับ booking engine (booking.py สร้าง base_slots) เป๊ะ:
    - override.is_unavailable                → ปิดทั้งวัน (ไม่มี session)
    - override มี custom_start_time + end    → **REPLACE** ใช้ช่วง custom แทนตารางปกติทั้งหมด
      (เปิด "วันทำงานพิเศษ" ที่ปกติปิดได้ — weekly ว่างก็ยังได้ session จาก custom window)
    - ไม่มี override (หรือ override ไม่มี custom hours) → ใช้ weekly blocks ตามปกติ (รองรับ multi-block)

    weekly_by_dow: {dow_value: [(start_time, end_time), ...]} จาก availabilities ของ template
    """
    override = _relevant_override(db, template_id, target_date)
    if override is not None and override.is_unavailable:
        return {}  # ปิดทั้งวัน → ไม่มี session
    if override is not None and override.custom_start_time and override.custom_end_time:
        start, end = override.custom_start_time, override.custom_end_time
        if start >= end:
            return {}  # ข้อมูลผิด (เริ่ม >= จบ) — ไม่สร้าง session
        return {_session_name(start, end): (start, end)}  # REPLACE ทั้งวันด้วยช่วง custom

    blocks = weekly_by_dow.get(_dow_value(target_date), [])
    # dedup ตามชื่อ (กันสองบล็อกเวลาซ้ำกันชนกันบน UNIQUE constraint)
    return {_session_name(bs, be): (bs, be) for bs, be in blocks}


def _has_references(db, session_id) -> bool:
    """session นี้ถูกอ้างอิงแล้วหรือยัง — history guard: ถ้ามี queue_entries หรือ appointment
    ผูกอยู่ ห้ามแก้เวลา/ปิด/ลบ (กันข้อมูลในอดีต + นัดที่จองไว้แล้วเสียหาย)"""
    if (db.query(models.QueueEntry.id)
            .filter(models.QueueEntry.session_id == session_id).first()) is not None:
        return True
    if (db.query(models.Appointment.id)
            .filter(models.Appointment.session_id == session_id).first()) is not None:
        return True
    return False


def generate_sessions(db, service_point_id: int,
                      date_from: datetime.date,
                      date_to: datetime.date) -> list:
    """Materialize sessions ของ service_point ในช่วง [date_from, date_to] (รวมปลายทั้งสอง)

    ขั้นตอน (แผน §5.8):
      1. ดึง availability template ของ service_point (ผ่าน availability_template_id)
      2. apply weekly pattern → session block ต่อวัน (รองรับ multi-block)
      3. apply date_overrides (template-specific) ทับ
      UPSERT เข้า sessions (UNIQUE service_point_id, session_date, name) → idempotent
      ห้ามแก้ session ที่มี queue_entries (history guard)

    คืน list ของ ServiceSession ที่ materialize ในช่วงนี้ (ทั้งที่สร้างใหม่และที่มีอยู่แล้ว)
    """
    if date_from > date_to:
        return []

    sp = db.query(models.ServicePoint).filter_by(id=service_point_id).one_or_none()
    if sp is None or sp.availability_template_id is None:
        return []  # ไม่มี service_point หรือยังไม่ map template → ไม่มี source ของเวลาทำการ

    template_id = sp.availability_template_id
    template = (db.query(models.AvailabilityTemplate)
                .filter_by(id=template_id)
                .one_or_none())
    if template is None or not template.is_active:
        return []  # template ถูกปิด → ไม่ generate (สอดคล้องกับการไม่เปิดให้จอง)

    # weekly pattern: {dow_value: [(start, end), ...]} — รองรับหลายบล็อก/วัน
    weekly_rows = (db.query(models.Availability)
                   .filter(models.Availability.template_id == template_id,
                           models.Availability.is_active == True)  # noqa: E712
                   .all())
    weekly_by_dow = {}
    for row in weekly_rows:
        dow = row.day_of_week.value if hasattr(row.day_of_week, 'value') else row.day_of_week
        weekly_by_dow.setdefault(dow, []).append((row.start_time, row.end_time))

    result = []
    current = date_from
    one_day = datetime.timedelta(days=1)
    while current <= date_to:
        desired = _desired_blocks_for_date(weekly_by_dow, db, template_id, current)

        # session ที่มีอยู่แล้วของ (sp, วันนี้) — index by name
        existing = {
            s.name: s
            for s in db.query(models.ServiceSession)
                       .filter(models.ServiceSession.service_point_id == service_point_id,
                               models.ServiceSession.session_date == current)
                       .all()
        }

        for name, (start, end) in desired.items():
            sess = existing.get(name)
            if sess is None:
                sess = models.ServiceSession(
                    service_point_id=service_point_id,
                    session_date=current,
                    name=name,
                    start_time=start,
                    end_time=end,
                    capacity=None,        # NULL = ไม่จำกัด (จับคิวแบบ window); throughput คุมด้วย parallel_servers
                    is_active=True,
                )
                db.add(sess)
            else:
                # history guard: ถ้ามี queue/appointment ผูกแล้ว ห้ามแก้เวลา/สถานะ (1B.4)
                if not _has_references(db, sess.id):
                    sess.start_time = start
                    sess.end_time = end
                    sess.is_active = True   # reactivate ถ้าเคยถูกปิดไว้แล้วบล็อกกลับมา
            result.append(sess)

        # change propagation: บล็อกที่หายไปจาก template (name ไม่อยู่ใน desired แล้ว)
        # → ปิด session กำพร้าที่ "ยังไม่มีใครจอง/เข้าคิว" (soft-deactivate ไม่ hard delete
        # เพื่อเลี่ยง FK + เก็บ history); ที่มี reference แล้วไม่แตะ
        for name, sess in existing.items():
            if name not in desired and sess.is_active and not _has_references(db, sess.id):
                sess.is_active = False

        current += one_day

    db.flush()
    db.commit()   # write ที่ท้ายงาน — after_begin (database.py) คุม search_path ของ txn ถัดไป
    return result


def sync_sessions_rolling(db, days_ahead: int = 14,
                          start: datetime.date = None) -> dict:
    """Regenerate sessions ช่วง [start, start + days_ahead] (รวมปลาย) สำหรับทุก active
    service_point ที่ map template แล้ว — เรียกจาก scheduler รายวัน หรือ trigger ตอน save

    ทำงาน "ต่อ tenant" บน session ที่ผูก tenant แล้ว (Celery task / g.db) — ไม่ข้าม schema เอง
    future-only โดยธรรมชาติ (start default = วันนี้); generate_sessions รักษา history ให้แล้ว

    คืน summary {'service_points': n, 'sessions': m, 'date_from':..., 'date_to':...}
    """
    start = start or today()
    end = start + datetime.timedelta(days=days_ahead)

    sps = (db.query(models.ServicePoint)
           .filter(models.ServicePoint.is_active == True,                    # noqa: E712
                   models.ServicePoint.availability_template_id.isnot(None))
           .all())

    total_sessions = 0
    for sp in sps:
        out = generate_sessions(db, sp.id, start, end)
        total_sessions += len(out)

    return {
        'service_points': len(sps),
        'sessions': total_sessions,
        'date_from': start,
        'date_to': end,
    }


def resync_template(db, template_id: int, days_ahead: int = 14,
                    start: datetime.date = None) -> dict:
    """Re-generate sessions ของทุก active service_point ที่ map กับ template นี้ (1B.3)

    เรียกเมื่อ availability/date_override ของ template ถูกแก้ — generate_sessions รักษา
    history ให้แล้ว (ไม่แตะ session ที่มี queue/appointment) + future-only (start=วันนี้)
    """
    start = start or today()
    end = start + datetime.timedelta(days=days_ahead)

    sps = (db.query(models.ServicePoint)
           .filter(models.ServicePoint.is_active == True,                    # noqa: E712
                   models.ServicePoint.availability_template_id == template_id)
           .all())

    total_sessions = 0
    for sp in sps:
        total_sessions += len(generate_sessions(db, sp.id, start, end))

    return {
        'service_points': len(sps),
        'sessions': total_sessions,
        'date_from': start,
        'date_to': end,
    }


def resync_template_sessions_job(schema_name: str, template_id: int,
                                 days_ahead: int = 14) -> dict:
    """RQ entry point (1B.3): trigger จาก FastAPI ตอน save availability/override

    pure — ไม่ต้องมี Flask app context (พึ่งแค่ shared_db). enqueue ด้วย dotted-path
    'app.services.session_service.resync_template_sessions_job' จาก FastAPI โดยไม่ import flask_app
    (worker.py ใส่ flask_app/ ลง sys.path → 'app' = flask_app/app)

    ผูก tenant เอง (job ทำงานนอก request) แล้วคืน connection สะอาดตาม teardown pattern
    """
    db = SessionLocal()
    try:
        bind_tenant(db, schema_name)
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        return resync_template(db, template_id, days_ahead=days_ahead)
    except Exception:
        db.rollback()
        raise
    finally:
        # คืน connection สะอาด: ปลด tenant binding → ป้องกัน search_path ค้างข้าม tenant
        bind_tenant(db, None)
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def deactivate_future_sessions(db, service_point_id: int, start: datetime.date = None) -> int:
    """soft-deactivate future sessions ของ service_point ที่ไม่มี ref (queue_entries/appointment)

    ใช้ตอน service_point ถูก unmap จาก template (ลบ template → FK SET NULL): generator/rolling-sync
    จะข้าม sp ที่ไม่มี template → ถ้าไม่ปิด session อนาคตที่เคย generate ไว้จะค้าง active ทั้งที่ไม่มี
    availability รองรับ (P2). ไม่แตะอดีต (session_date < start) + ไม่แตะ session ที่มี ref (history guard)
    reversible: ถ้า sp ถูก map ใหม่ภายหลัง generate_sessions จะ reactivate session ที่ตรงให้เอง

    หมายเหตุ: FastAPI delete_availability_template ทำ cleanup นี้ **inline แบบ synchronous+atomic** เอง
    (import ฟังก์ชันนี้ตรงไม่ได้—จะโหลด flask_app/app/__init__.py = Flask app factory) — logic ต้อง mirror กัน

    คืนจำนวน session ที่ถูกปิด
    """
    start = start or today()
    rows = (db.query(models.ServiceSession)
            .filter(models.ServiceSession.service_point_id == service_point_id,
                    models.ServiceSession.session_date >= start,
                    models.ServiceSession.is_active == True)   # noqa: E712
            .all())
    n = 0
    for s in rows:
        if not _has_references(db, s.id):
            s.is_active = False
            n += 1
    db.commit()
    return n


def resync_tenant_sessions_job(schema_name: str, days_ahead: int = 14) -> dict:
    """RQ entry point (1B.3): re-sync ทุก active service_point ของ tenant

    ใช้ตอน **global date_override** เปลี่ยน (ไม่ผูก template ใด template หนึ่ง → กระทบทุก sp) —
    trigger จาก FastAPI create/delete date_override ที่ template_scope='global'
    pure (พึ่งแค่ shared_db); ผูก tenant เอง แล้วคืน connection สะอาดตาม teardown pattern
    """
    db = SessionLocal()
    try:
        bind_tenant(db, schema_name)
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        return sync_sessions_rolling(db, days_ahead=days_ahead)
    except Exception:
        db.rollback()
        raise
    finally:
        bind_tenant(db, None)
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()
