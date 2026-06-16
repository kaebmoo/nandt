"""
Unit tests สำหรับ session_service.generate_sessions (แผน 9.2 / Phase 1B.1 + 1B.4):
- idempotent UPSERT: รัน 2 ครั้งไม่เกิด session ซ้ำ
- multi-block/วัน → หลาย session (เช่น จันทร์ 2 ช่วง)
- date_override custom window → clamp เวลา session ถูกต้อง
- date_override is_unavailable → ไม่มี session วันนั้น
- weekday mapping ตรงกับ booking (เสาร์/อาทิตย์)
- history guard: session ที่มี queue_entries แล้ว ห้ามถูกแก้
- service_point ที่ไม่ได้ map template → ไม่มี session
"""

import datetime

import pytest

from shared_db import models
from flask_app.app.services import session_service as ss

T = datetime.time


# ---------- helpers ----------

def _make_template(db, name="tpl", active=True):
    tpl = models.AvailabilityTemplate(name=name, is_active=active)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def _add_availability(db, template_id, target_date, start, end):
    """เพิ่ม weekly availability สำหรับ weekday ของ target_date"""
    dow = models.DayOfWeek(ss._dow_value(target_date))
    db.add(models.Availability(
        template_id=template_id,
        day_of_week=dow,
        start_time=start,
        end_time=end,
        is_active=True,
    ))
    db.commit()


def _map_sp(db, service_point, template_id):
    service_point.availability_template_id = template_id
    db.commit()
    db.refresh(service_point)


def _sessions(db, sp_id, d):
    return (db.query(models.ServiceSession)
            .filter_by(service_point_id=sp_id, session_date=d)
            .order_by(models.ServiceSession.start_time)
            .all())


# ใช้วันจันทร์เป็นฐาน (มี availability) — คำนวณ weekday จริงด้วย _dow_value ใน helper
MON = datetime.date(2026, 6, 15)   # จันทร์
SAT = datetime.date(2026, 6, 13)   # เสาร์
SUN = datetime.date(2026, 6, 14)   # อาทิตย์


# ---------- basic generate ----------

def test_single_block_creates_one_session(db, service_point):
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    out = ss.generate_sessions(db, service_point.id, MON, MON)

    rows = _sessions(db, service_point.id, MON)
    assert len(rows) == 1
    assert rows[0].name == "08:30-16:30"
    assert rows[0].start_time == T(8, 30)
    assert rows[0].end_time == T(16, 30)
    assert rows[0].capacity is None
    assert len(out) == 1


def test_multi_block_day_creates_two_sessions(db, service_point):
    """จันทร์ 2 ช่วง (เหมือน template 61) → 2 session แยกตามชื่อช่วงเวลา"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _add_availability(db, tpl.id, MON, T(17, 0), T(20, 0))
    _map_sp(db, service_point, tpl.id)

    ss.generate_sessions(db, service_point.id, MON, MON)

    rows = _sessions(db, service_point.id, MON)
    assert [r.name for r in rows] == ["08:30-16:30", "17:00-20:00"]
    assert [(r.start_time, r.end_time) for r in rows] == [
        (T(8, 30), T(16, 30)),
        (T(17, 0), T(20, 0)),
    ]


# ---------- idempotency ----------

def test_idempotent_no_duplicate_on_rerun(db, service_point):
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _add_availability(db, tpl.id, MON, T(17, 0), T(20, 0))
    _map_sp(db, service_point, tpl.id)

    ss.generate_sessions(db, service_point.id, MON, MON)
    ss.generate_sessions(db, service_point.id, MON, MON)
    ss.generate_sessions(db, service_point.id, MON, MON)

    rows = _sessions(db, service_point.id, MON)
    assert len(rows) == 2   # ยังคง 2 ไม่ทวีคูณ


# ---------- date_override ----------

def test_override_custom_window_replaces_session(db, service_point):
    """custom 09:00-12:00 REPLACE weekly 08:30-16:30 → session = 09:00-12:00 (ตรง booking)"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)
    db.add(models.DateOverride(
        template_id=tpl.id, date=MON, template_scope='template',
        is_unavailable=False, custom_start_time=T(9, 0), custom_end_time=T(12, 0),
    ))
    db.commit()

    ss.generate_sessions(db, service_point.id, MON, MON)

    rows = _sessions(db, service_point.id, MON)
    assert len(rows) == 1
    assert rows[0].name == "09:00-12:00"
    assert rows[0].start_time == T(9, 0)
    assert rows[0].end_time == T(12, 0)


def test_override_unavailable_yields_no_session(db, service_point):
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)
    db.add(models.DateOverride(
        template_id=tpl.id, date=MON, template_scope='template', is_unavailable=True,
    ))
    db.commit()

    ss.generate_sessions(db, service_point.id, MON, MON)

    assert _sessions(db, service_point.id, MON) == []


def test_override_replaces_even_outside_weekly(db, service_point):
    """custom 18:00-20:00 REPLACE weekly 08:30-16:30 → session = 18:00-20:00 (ไม่ใช่ intersect)"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)
    db.add(models.DateOverride(
        template_id=tpl.id, date=MON, template_scope='template',
        custom_start_time=T(18, 0), custom_end_time=T(20, 0),
    ))
    db.commit()

    ss.generate_sessions(db, service_point.id, MON, MON)

    rows = _sessions(db, service_point.id, MON)
    assert len(rows) == 1
    assert rows[0].name == "18:00-20:00"


def test_override_opens_normally_closed_day(db, service_point):
    """วันทำงานพิเศษ (A2): weekly เปิดแค่จันทร์ แต่ override custom hours วันเสาร์ → เสาร์มี session"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))   # weekly: จันทร์อย่างเดียว
    _map_sp(db, service_point, tpl.id)
    db.add(models.DateOverride(
        template_id=tpl.id, date=SAT, template_scope='template',   # เสาร์ปกติปิด
        custom_start_time=T(9, 0), custom_end_time=T(12, 0),
    ))
    db.commit()

    ss.generate_sessions(db, service_point.id, SAT, SAT)

    rows = _sessions(db, service_point.id, SAT)
    assert len(rows) == 1
    assert rows[0].name == "09:00-12:00"
    assert rows[0].start_time == T(9, 0)
    assert rows[0].end_time == T(12, 0)


# ---------- weekday mapping ----------

def test_no_availability_for_weekday_yields_no_session(db, service_point):
    """availability เฉพาะจันทร์ → generate วันเสาร์/อาทิตย์ ต้องไม่มี session (mapping ถูก)"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    ss.generate_sessions(db, service_point.id, SAT, SUN)

    assert _sessions(db, service_point.id, SAT) == []
    assert _sessions(db, service_point.id, SUN) == []


def test_dow_value_matches_booking_convention():
    """Python weekday → DayOfWeek value (Sun=0, Mon=1..Sat=6) — ตรงกับ convert_python_weekday"""
    assert ss._dow_value(MON) == models.DayOfWeek.MONDAY.value == 1
    assert ss._dow_value(SAT) == models.DayOfWeek.SATURDAY.value == 6
    assert ss._dow_value(SUN) == models.DayOfWeek.SUNDAY.value == 0


# ---------- history guard (1B.4) ----------

def test_session_with_queue_entries_not_modified(db, service_point):
    """session ที่มี queue_entries แล้ว ห้ามถูกแก้เวลา แม้ generator จะคำนวณค่าใหม่"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    # สร้าง session ชื่อ "08:30-16:30" แต่ start_time ผิด (07:00) + แนบ queue_entry
    sess = models.ServiceSession(
        service_point_id=service_point.id, session_date=MON, name="08:30-16:30",
        start_time=T(7, 0), end_time=T(16, 30), is_active=True,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    db.add(models.QueueEntry(
        service_point_id=service_point.id, session_id=sess.id, session_date=MON,
        patient_ref="phone:+66860000001", entry_class='walkin', status='checked_in',
    ))
    db.commit()
    sess_id = sess.id

    ss.generate_sessions(db, service_point.id, MON, MON)

    guarded = db.query(models.ServiceSession).filter_by(id=sess_id).one()
    assert guarded.start_time == T(7, 0)   # ไม่ถูกแก้ (มีคิวผูกแล้ว)
    # ไม่เกิดแถวซ้ำชื่อเดิม
    assert len(_sessions(db, service_point.id, MON)) == 1


def test_session_without_queue_entries_is_corrected(db, service_point):
    """ในทางกลับกัน: ถ้าไม่มี queue_entries generator แก้เวลาให้ตรง template ได้ (idempotent reconcile)"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    sess = models.ServiceSession(
        service_point_id=service_point.id, session_date=MON, name="08:30-16:30",
        start_time=T(7, 0), end_time=T(16, 30), is_active=True,
    )
    db.add(sess)
    db.commit()
    sess_id = sess.id

    ss.generate_sessions(db, service_point.id, MON, MON)

    fixed = db.query(models.ServiceSession).filter_by(id=sess_id).one()
    assert fixed.start_time == T(8, 30)   # ถูกแก้ให้ตรง template


# ---------- guards ----------

def test_service_point_without_template_yields_nothing(db, service_point):
    out = ss.generate_sessions(db, service_point.id, MON, MON)
    assert out == []
    assert _sessions(db, service_point.id, MON) == []


def test_deleting_mapped_template_sets_sp_unmapped(db, service_point):
    """P1: ลบ availability_template ที่ map กับ service_point → sp.availability_template_id = NULL
    (FK ON DELETE SET NULL) ไม่ FK-violation; sp ยังอยู่"""
    tpl = _make_template(db)
    _map_sp(db, service_point, tpl.id)
    assert service_point.availability_template_id == tpl.id

    db.delete(db.query(models.AvailabilityTemplate).filter_by(id=tpl.id).one())
    db.commit()

    sp = db.query(models.ServicePoint).filter_by(id=service_point.id).one()
    assert sp is not None                          # sp ไม่ถูกลบตาม
    assert sp.availability_template_id is None      # ถูก SET NULL


def test_inactive_template_yields_nothing(db, service_point):
    tpl = _make_template(db, active=False)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    out = ss.generate_sessions(db, service_point.id, MON, MON)
    assert out == []
    assert _sessions(db, service_point.id, MON) == []


# ---------- sync_sessions_rolling (1B.2 core) ----------

def test_rolling_sync_covers_window_for_active_mapped_sp(db, service_point):
    """sync สร้าง session ครบทุกวันทำการในช่วง [start, start+days_ahead]"""
    tpl = _make_template(db)
    # availability ทุกวันจันทร์-อาทิตย์ เพื่อให้ทุกวันในช่วงมี session (ทดสอบ coverage)
    for d in (MON, datetime.date(2026, 6, 16), datetime.date(2026, 6, 17),
              datetime.date(2026, 6, 18), datetime.date(2026, 6, 19), SAT, SUN):
        _add_availability(db, tpl.id, d, T(9, 0), T(17, 0))
    _map_sp(db, service_point, tpl.id)

    summary = ss.sync_sessions_rolling(db, days_ahead=6, start=MON)

    assert summary['service_points'] == 1
    # 7 วัน (MON..SUN) × 1 บล็อก = 7 session
    total = (db.query(models.ServiceSession)
             .filter_by(service_point_id=service_point.id).count())
    assert total == 7
    assert summary['sessions'] == 7
    assert summary['date_from'] == MON
    assert summary['date_to'] == MON + datetime.timedelta(days=6)


def test_rolling_sync_skips_unmapped_and_inactive_sp(db):
    """service_point ที่ไม่ได้ map template หรือ inactive ต้องถูกข้าม"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(9, 0), T(17, 0))

    mapped = models.ServicePoint(name="mapped", sp_type="counter", parallel_servers=1,
                                 availability_template_id=tpl.id)
    unmapped = models.ServicePoint(name="unmapped", sp_type="counter", parallel_servers=1)
    inactive = models.ServicePoint(name="inactive", sp_type="counter", parallel_servers=1,
                                   availability_template_id=tpl.id, is_active=False)
    db.add_all([mapped, unmapped, inactive])
    db.commit()

    summary = ss.sync_sessions_rolling(db, days_ahead=0, start=MON)

    assert summary['service_points'] == 1   # เฉพาะ mapped + active
    assert (db.query(models.ServiceSession)
            .filter_by(service_point_id=mapped.id).count()) == 1
    assert (db.query(models.ServiceSession)
            .filter_by(service_point_id=unmapped.id).count()) == 0
    assert (db.query(models.ServiceSession)
            .filter_by(service_point_id=inactive.id).count()) == 0


def test_rolling_sync_idempotent(db, service_point):
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(9, 0), T(17, 0))
    _map_sp(db, service_point, tpl.id)

    ss.sync_sessions_rolling(db, days_ahead=0, start=MON)
    ss.sync_sessions_rolling(db, days_ahead=0, start=MON)

    assert (db.query(models.ServiceSession)
            .filter_by(service_point_id=service_point.id).count()) == 1


# ---------- change propagation / prune (1B.3) ----------

def test_orphan_session_without_refs_is_deactivated(db, service_point):
    """บล็อกที่หายไปจาก template → session กำพร้าที่ไม่มีคนจอง ถูกปิด (is_active=False)"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    # session เก่าที่ไม่อยู่ใน template (เช่น เคย generate ตอน availability เป็นแบบอื่น)
    orphan = models.ServiceSession(
        service_point_id=service_point.id, session_date=MON, name="07:00-08:00",
        start_time=T(7, 0), end_time=T(8, 0), is_active=True,
    )
    db.add(orphan)
    db.commit()
    orphan_id = orphan.id

    ss.generate_sessions(db, service_point.id, MON, MON)

    rows = {r.name: r for r in _sessions(db, service_point.id, MON)}
    assert rows["08:30-16:30"].is_active is True       # บล็อกปัจจุบัน
    assert rows["07:00-08:00"].is_active is False       # กำพร้า → ปิด (ไม่ลบ)
    assert db.query(models.ServiceSession).filter_by(id=orphan_id).one().is_active is False


def test_orphan_session_with_queue_entries_is_preserved(db, service_point):
    """session กำพร้าที่ "มีคนเข้าคิวแล้ว" ห้ามถูกปิด/ลบ — รักษา history"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    orphan = models.ServiceSession(
        service_point_id=service_point.id, session_date=MON, name="07:00-08:00",
        start_time=T(7, 0), end_time=T(8, 0), is_active=True,
    )
    db.add(orphan)
    db.commit()
    db.refresh(orphan)
    db.add(models.QueueEntry(
        service_point_id=service_point.id, session_id=orphan.id, session_date=MON,
        patient_ref="phone:+66860000001", entry_class='walkin', status='checked_in',
    ))
    db.commit()
    orphan_id = orphan.id

    ss.generate_sessions(db, service_point.id, MON, MON)

    assert db.query(models.ServiceSession).filter_by(id=orphan_id).one().is_active is True


def test_orphan_session_with_appointment_is_preserved(db, service_point):
    """session กำพร้าที่มี appointment ผูกอยู่ (จองแล้วแต่ยังไม่ check-in) ก็ห้ามปิด"""
    tpl = _make_template(db)
    _add_availability(db, tpl.id, MON, T(8, 30), T(16, 30))
    _map_sp(db, service_point, tpl.id)

    orphan = models.ServiceSession(
        service_point_id=service_point.id, session_date=MON, name="07:00-08:00",
        start_time=T(7, 0), end_time=T(8, 0), is_active=True,
    )
    db.add(orphan)
    db.commit()
    db.refresh(orphan)
    db.add(models.Appointment(
        session_id=orphan.id, service_point_id=service_point.id,
        start_time=datetime.datetime(2026, 6, 15, 7, 30),
        end_time=datetime.datetime(2026, 6, 15, 8, 0),
        status='confirmed',
    ))
    db.commit()
    orphan_id = orphan.id

    ss.generate_sessions(db, service_point.id, MON, MON)

    assert db.query(models.ServiceSession).filter_by(id=orphan_id).one().is_active is True


# ---------- resync_template (1B.3 core) ----------

def test_deactivate_future_sessions_unmapped_sp(db, service_point):
    """P2: ปิด future sessions ที่ไม่มี ref; ไม่แตะอดีต + ไม่แตะ session ที่มีคิว"""
    PAST = datetime.date(2026, 6, 10)   # < today (2026-06-14)
    FUT1 = datetime.date(2026, 6, 20)
    FUT2 = datetime.date(2026, 6, 21)

    def _sess(d, name):
        s = models.ServiceSession(service_point_id=service_point.id, session_date=d, name=name,
                                  start_time=T(9, 0), end_time=T(12, 0), is_active=True)
        db.add(s); db.commit(); db.refresh(s)
        return s

    past = _sess(PAST, "09:00-12:00")
    fut_orphan = _sess(FUT1, "09:00-12:00")
    fut_withqueue = _sess(FUT2, "09:00-12:00")
    db.add(models.QueueEntry(service_point_id=service_point.id, session_id=fut_withqueue.id,
                             session_date=FUT2, patient_ref="phone:+66860000001", entry_class='walkin', status='checked_in'))
    db.commit()

    n = ss.deactivate_future_sessions(db, service_point.id, start=datetime.date(2026, 6, 14))

    assert n == 1   # เฉพาะ fut_orphan
    assert db.query(models.ServiceSession).filter_by(id=past.id).one().is_active is True          # อดีตไม่แตะ
    assert db.query(models.ServiceSession).filter_by(id=fut_orphan.id).one().is_active is False     # ปิด
    assert db.query(models.ServiceSession).filter_by(id=fut_withqueue.id).one().is_active is True   # มีคิว → คงไว้


def test_resync_template_only_touches_mapped_active_sps(db):
    tpl_a = _make_template(db, name="A")
    tpl_b = _make_template(db, name="B")
    _add_availability(db, tpl_a.id, MON, T(9, 0), T(17, 0))
    _add_availability(db, tpl_b.id, MON, T(9, 0), T(17, 0))

    sp1 = models.ServicePoint(name="sp1", sp_type="counter", parallel_servers=1,
                              availability_template_id=tpl_a.id)
    sp2 = models.ServicePoint(name="sp2", sp_type="counter", parallel_servers=1,
                              availability_template_id=tpl_a.id)
    sp_other = models.ServicePoint(name="other", sp_type="counter", parallel_servers=1,
                                   availability_template_id=tpl_b.id)
    db.add_all([sp1, sp2, sp_other])
    db.commit()

    summary = ss.resync_template(db, tpl_a.id, days_ahead=0, start=MON)

    assert summary['service_points'] == 2   # เฉพาะ sp ที่ map tpl_a
    assert (db.query(models.ServiceSession).filter_by(service_point_id=sp1.id).count()) == 1
    assert (db.query(models.ServiceSession).filter_by(service_point_id=sp2.id).count()) == 1
    assert (db.query(models.ServiceSession).filter_by(service_point_id=sp_other.id).count()) == 0
