"""Unit tests สำหรับ priority_service (Phase 2.3-2.4):
- ratio interleaving: เรียก appointment ครบ ratio แล้วแทรก walk-in
- starvation guard: walk-in ที่รอนานเกิน threshold ถูกดันขึ้นก่อน
- score mode: appointment ใน window ชนะ walk-in; walk-in ที่รอนานมากชนะในที่สุด
"""

import datetime

from shared_db import models
from flask_app.app.services import priority_service as ps

DT = datetime.datetime


def _policy(db, sp_id=None, mode='ratio', ratio=3, max_wait=45, call_timeout=5,
            w_class=100, w_wait=1, w_window=2):
    pol = models.QueuePolicy(
        service_point_id=sp_id,
        mode=mode,
        appointment_to_walkin_ratio=ratio,
        walkin_max_wait_minutes=max_wait,
        appointment_early_eligible_minutes=15,
        call_timeout_min=call_timeout,
        w_class=w_class,
        w_wait=w_wait,
        w_window=w_window,
    )
    db.add(pol)
    db.commit()
    return pol


def _appt(db, sp_id, start=DT(2026, 6, 15, 9, 0), end=DT(2026, 6, 15, 9, 30)):
    appt = models.Appointment(
        service_point_id=sp_id,
        start_time=start,
        end_time=end,
        status='confirmed',
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def _entry(db, sp_id, day, qno, entry_class, check_in_at, status='checked_in', appointment=None,
           called_at=None):
    entry = models.QueueEntry(
        appointment_id=appointment.id if appointment is not None else None,
        service_point_id=sp_id,
        session_date=day,
        patient_ref=f"phone:+6683000{qno:04d}",
        entry_class=entry_class,
        queue_number=qno,
        status=status,
        check_in_at=check_in_at,
        called_at=called_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_ratio_interleaves_walkin_after_three_appointments(db, service_point):
    _policy(db, ratio=3)
    day = datetime.date(2026, 6, 15)
    now = DT(2026, 6, 15, 9, 10)

    # recent call history: appointment, appointment, appointment
    for i, minute in enumerate((1, 2, 3), start=1):
        _entry(db, service_point.id, day, i, 'appointment', now, status='done',
               called_at=DT(2026, 6, 15, 8, minute))

    appt = _appt(db, service_point.id)
    _entry(db, service_point.id, day, 4, 'appointment', now, appointment=appt)
    walkin = _entry(db, service_point.id, day, 5, 'walkin', now)

    chosen = ps.call_next(db, service_point.id, day, now=now)

    assert chosen.id == walkin.id
    assert chosen.status == 'called'


def test_starving_walkin_is_called_before_eligible_appointment(db, service_point):
    _policy(db, max_wait=45)
    day = datetime.date(2026, 6, 15)
    now = DT(2026, 6, 15, 9, 30)
    appt = _appt(db, service_point.id, start=DT(2026, 6, 15, 9, 0), end=DT(2026, 6, 15, 9, 30))
    _entry(db, service_point.id, day, 1, 'appointment', now, appointment=appt)
    walkin = _entry(db, service_point.id, day, 2, 'walkin', DT(2026, 6, 15, 8, 0))

    chosen = ps.call_next(db, service_point.id, day, now=now)

    assert chosen.id == walkin.id


def test_score_mode_appointment_in_window_beats_walkin(db, service_point):
    _policy(db, mode='score', max_wait=999, w_class=100, w_wait=1, w_window=2)
    day = datetime.date(2026, 6, 15)
    now = DT(2026, 6, 15, 9, 10)
    appt = _appt(db, service_point.id, start=DT(2026, 6, 15, 9, 0), end=DT(2026, 6, 15, 9, 30))
    appt_entry = _entry(db, service_point.id, day, 1, 'appointment', now, appointment=appt)
    _entry(db, service_point.id, day, 2, 'walkin', now)

    chosen = ps.call_next(db, service_point.id, day, now=now)

    assert chosen.id == appt_entry.id


def test_score_mode_long_waiting_walkin_eventually_wins(db, service_point):
    _policy(db, mode='score', max_wait=999, w_class=100, w_wait=1, w_window=0)
    day = datetime.date(2026, 6, 15)
    now = DT(2026, 6, 15, 9, 10)
    appt = _appt(db, service_point.id, start=DT(2026, 6, 15, 9, 0), end=DT(2026, 6, 15, 9, 30))
    _entry(db, service_point.id, day, 1, 'appointment', now, appointment=appt)
    walkin = _entry(db, service_point.id, day, 2, 'walkin', DT(2026, 6, 15, 5, 0))

    chosen = ps.call_next(db, service_point.id, day, now=now)

    assert chosen.id == walkin.id


def test_call_next_closes_stale_called_before_capacity_count(db, service_point):
    _policy(db, call_timeout=5)
    day = datetime.date(2026, 6, 15)
    now = DT(2026, 6, 15, 9, 6)
    stale = _entry(
        db,
        service_point.id,
        day,
        1,
        'walkin',
        DT(2026, 6, 15, 8, 50),
        status='called',
        called_at=DT(2026, 6, 15, 9, 0),
    )
    waiting = _entry(db, service_point.id, day, 2, 'walkin', DT(2026, 6, 15, 9, 1))

    chosen = ps.call_next(db, service_point.id, day, now=now)

    db.refresh(stale)
    assert stale.status == 'no_show'
    assert chosen.id == waiting.id
    assert chosen.status == 'called'
    stale_event = (db.query(models.QueueEvent)
                   .filter_by(queue_entry_id=stale.id)
                   .order_by(models.QueueEvent.id.desc())
                   .one())
    assert stale_event.event_type == 'no_show'
    assert stale_event.event_metadata == {'reason': 'called_timeout', 'call_timeout_min': 5}
