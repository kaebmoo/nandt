"""Unit tests สำหรับ grace_service (แผน 9.2 / Phase 2.1–2.2):
- classify_on_checkin ครบเคส: in-window / early / same-day-late / cross-session / require_rebook / reslot
- get_grace_policy fallback (sp-specific → tenant default)
- integration: check_in นัดที่มาสาย → entry_class='walkin' + queue_events('reclass')
"""

import datetime

import pytest

from shared_db import models
from flask_app.app.services import grace_service as gs
from flask_app.app.services import queue_service as qs

DT = datetime.datetime
T = datetime.time


def _phone(n):
    return f"082000{n:04d}"


def _appt(start, end, session_id=None):
    """Appointment instance (ไม่ persist) สำหรับเทส classify ล้วน ๆ"""
    return models.Appointment(start_time=start, end_time=end, session_id=session_id)


def _policy(before=30, after=30, late='demote_to_walkin'):
    return models.GracePolicy(grace_before_min=before, grace_after_min=after, late_arrival_policy=late)


# ---------- classify_on_checkin (pure, ไม่แตะ DB) ----------

def test_in_window_keeps_appointment():
    appt = _appt(DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))
    # slot 09:00-09:30, grace 30/30 → window [08:30, 10:00]
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 9, 15), _policy()) == 'appointment'
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 8, 30), _policy()) == 'appointment'  # ขอบเริ่ม
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 10, 0), _policy()) == 'appointment'  # ขอบจบ


def test_early_arrival_not_punished():
    """มาก่อนช่วงผ่อนผันมาก → ยังเป็น appointment (ไม่ลงโทษการมาเช้า)"""
    appt = _appt(DT(2026, 6, 15, 14, 0), DT(2026, 6, 15, 14, 30))
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 9, 0), _policy()) == 'appointment'


def test_same_day_late_demotes_to_walkin():
    """มาสายเกินช่วง (วันเดียวกัน) + นโยบาย default → demote เป็น walkin"""
    appt = _appt(DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 11, 0), _policy()) == 'walkin'


def test_cross_session_late_demotes(db):
    """จองช่วงเช้า (window=session 08:30-12:00) มาบ่าย 14:00 → สายเกินช่วง → walkin"""
    sess = models.ServiceSession(start_time=T(8, 30), end_time=T(12, 0))
    appt = _appt(DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30), session_id=1)
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 14, 0), _policy(), session=sess) == 'walkin'
    # ในช่วง session ตอน 11:00 → ยังเป็น appointment
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 11, 0), _policy(), session=sess) == 'appointment'


def test_require_rebook_raises_on_late():
    appt = _appt(DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))
    with pytest.raises(gs.NoShowError):
        gs.classify_on_checkin(appt, DT(2026, 6, 15, 11, 0), _policy(late='require_rebook'))


def test_reslot_keeps_appointment_on_late():
    appt = _appt(DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 11, 0), _policy(late='reslot_to_current')) == 'appointment'


def test_no_slot_time_defaults_appointment():
    appt = _appt(None, None)
    assert gs.classify_on_checkin(appt, DT(2026, 6, 15, 11, 0), _policy()) == 'appointment'


# ---------- get_grace_policy fallback ----------

def test_get_grace_policy_prefers_sp_then_default(db, service_point):
    db.add(models.GracePolicy(service_point_id=None, grace_before_min=30, grace_after_min=30))
    db.commit()
    # ยังไม่มี policy ของ sp → ได้ default (sp_id None)
    pol = gs.get_grace_policy(db, service_point.id)
    assert pol is not None and pol.service_point_id is None

    db.add(models.GracePolicy(service_point_id=service_point.id, grace_before_min=10, grace_after_min=10))
    db.commit()
    pol = gs.get_grace_policy(db, service_point.id)
    assert pol.service_point_id == service_point.id and pol.grace_before_min == 10


# ---------- integration: check_in + grace + reclass event ----------

def _make_appt(db, sp_id, start, end):
    a = models.Appointment(
        start_time=start,
        end_time=end,
        service_point_id=sp_id,
        guest_phone=_phone(1),
        status='confirmed',
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _events(db, entry_id):
    return (db.query(models.QueueEvent)
            .filter_by(queue_entry_id=entry_id)
            .order_by(models.QueueEvent.id).all())


def test_checkin_late_appointment_demoted_with_reclass_event(db, service_point):
    db.add(models.GracePolicy(service_point_id=None, grace_before_min=30, grace_after_min=30,
                              late_arrival_policy='demote_to_walkin'))
    db.commit()
    appt = _make_appt(db, service_point.id, DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))

    entry = qs.check_in(db, appt.id, service_point.id, _phone(1), now=DT(2026, 6, 15, 11, 0))

    assert entry.entry_class == 'walkin'          # ถูก demote
    evs = _events(db, entry.id)
    types = [e.event_type for e in evs]
    assert 'check_in' in types and 'reclass' in types
    reclass = next(e for e in evs if e.event_type == 'reclass')
    assert reclass.event_metadata == {'from_class': 'appointment', 'to_class': 'walkin', 'reason': 'late'}


def test_checkin_ontime_appointment_keeps_priority_no_reclass(db, service_point):
    db.add(models.GracePolicy(service_point_id=None, grace_before_min=30, grace_after_min=30,
                              late_arrival_policy='demote_to_walkin'))
    db.commit()
    appt = _make_appt(db, service_point.id, DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))

    entry = qs.check_in(db, appt.id, service_point.id, _phone(1), now=DT(2026, 6, 15, 9, 10))

    assert entry.entry_class == 'appointment'
    assert [e.event_type for e in _events(db, entry.id)] == ['check_in']   # ไม่มี reclass


def test_checkin_require_rebook_rejects_late(db, service_point):
    db.add(models.GracePolicy(service_point_id=None, grace_before_min=30, grace_after_min=30,
                              late_arrival_policy='require_rebook'))
    db.commit()
    appt = _make_appt(db, service_point.id, DT(2026, 6, 15, 9, 0), DT(2026, 6, 15, 9, 30))

    with pytest.raises(gs.NoShowError):
        qs.check_in(db, appt.id, service_point.id, _phone(1), now=DT(2026, 6, 15, 11, 0))
