"""
Unit tests สำหรับ queue_service (แผน 9.2):
- transition + queue_events: ทุก transition มี event row + timestamp ลงถูก field
- check-in concurrency: queue_number ไม่ซ้ำเมื่อสแกนพร้อมกัน
"""

import datetime
import threading

import pytest

from shared_db import models
from flask_app.app.services import queue_service as qs

UTC = datetime.timezone.utc


def _phone(n):
    return f"081000{n:04d}"


# ---------- check_in ----------

def test_checkin_walkin_creates_entry_and_event(db, service_point):
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    entry = qs.check_in(db, None, service_point.id, _phone(1), now=now)

    assert entry.queue_number == 1
    assert entry.status == 'checked_in'
    assert entry.entry_class == 'walkin'
    assert entry.appointment_id is None
    assert entry.patient_ref == 'phone:+66810000001'
    assert entry.check_in_at is not None
    assert entry.session_date == datetime.date(2026, 6, 13)

    events = db.query(models.QueueEvent).filter_by(queue_entry_id=entry.id).all()
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == 'check_in'
    assert ev.from_status is None
    assert ev.to_status == 'checked_in'
    assert ev.actor == 'patient'
    assert ev.event_metadata == {'queue_number': 1, 'entry_class': 'walkin'}


def test_checkin_numbers_increment_per_service_point_date(db, service_point):
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    e1 = qs.check_in(db, None, service_point.id, _phone(1), now=now)
    e2 = qs.check_in(db, None, service_point.id, _phone(2), now=now)
    e3 = qs.check_in(db, None, service_point.id, _phone(3), now=now)
    assert [e1.queue_number, e2.queue_number, e3.queue_number] == [1, 2, 3]


def test_checkin_appointment_is_idempotent_while_active(db, service_point):
    appt = models.Appointment(
        guest_name="คนไข้ A",
        guest_phone=_phone(10),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    first = qs.check_in(db, appt.id, service_point.id, _phone(10))
    again = qs.check_in(db, appt.id, service_point.id, _phone(10))

    assert first.id == again.id                       # ไม่สร้าง entry ซ้ำ
    assert first.entry_class == 'appointment'
    assert first.session_date == datetime.date(2026, 6, 13)   # มาจาก appointment.start_time
    n_entries = db.query(models.QueueEntry).filter_by(appointment_id=appt.id).count()
    assert n_entries == 1


def test_checkin_appointment_uses_patient_id_as_canonical_ref(db, service_point):
    patient = models.Patient(name="คนไข้ canonical", phone_number=_phone(40))
    db.add(patient)
    db.commit()
    db.refresh(patient)
    appt = models.Appointment(
        patient_id=patient.id,
        guest_phone=_phone(41),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    entry = qs.check_in(db, appt.id, service_point.id, _phone(41))

    assert entry.patient_ref == f"patient:{patient.id}"


def _make_event_type(db, requires_queue):
    et = models.EventType(
        name=f"service-{requires_queue}",
        slug=f"service-{requires_queue}",
        duration_minutes=30,
        requires_queue=requires_queue,
    )
    db.add(et)
    db.commit()
    db.refresh(et)
    return et


def test_checkin_appointment_requires_queue_false_records_arrival_only(db, service_point):
    et = _make_event_type(db, requires_queue=False)
    db.add(models.GracePolicy(service_point_id=None, late_arrival_policy='require_rebook'))
    appt = models.Appointment(
        event_type_id=et.id,
        service_point_id=service_point.id,
        booking_reference="VN-NQ0001",
        guest_name="คนไข้ไม่เข้าคิว",
        guest_phone=_phone(11),
        start_time=datetime.datetime(2026, 6, 13, 9, 0),
        end_time=datetime.datetime(2026, 6, 13, 9, 30),
        status='confirmed',
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    result = qs.check_in(
        db,
        appt.id,
        service_point.id,
        _phone(11),
        now=datetime.datetime(2026, 6, 13, 11, 0, tzinfo=UTC),
    )

    assert isinstance(result, qs.ArrivalCheckInResult)
    assert result.appointment_id == appt.id
    assert result.queue_number is None
    assert db.query(models.QueueEntry).filter_by(appointment_id=appt.id).count() == 0
    assert db.query(models.QueueEvent).count() == 0
    db.refresh(appt)
    assert appt.status == 'confirmed'

    log = db.query(models.AuditLog).filter_by(
        action='check_in_arrival',
        resource_type='Appointment',
        resource_id=str(appt.id),
    ).one()
    assert log.details['requires_queue'] is False
    assert log.details['service_point_id'] == service_point.id
    assert log.details['booking_reference'] == "VN-NQ0001"


def test_checkin_appointment_requires_queue_true_uses_queue_path(db, service_point):
    et = _make_event_type(db, requires_queue=True)
    appt = models.Appointment(
        event_type_id=et.id,
        service_point_id=service_point.id,
        booking_reference="VN-Q0001",
        guest_name="คนไข้เข้าคิว",
        guest_phone=_phone(12),
        start_time=datetime.datetime(2026, 6, 13, 9, 0),
        end_time=datetime.datetime(2026, 6, 13, 9, 30),
        status='confirmed',
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    entry = qs.check_in(
        db,
        appt.id,
        service_point.id,
        _phone(12),
        now=datetime.datetime(2026, 6, 13, 9, 10, tzinfo=UTC),
    )

    assert isinstance(entry, models.QueueEntry)
    assert entry.queue_number == 1
    assert entry.entry_class == 'appointment'
    assert entry.status == 'checked_in'
    assert db.query(models.QueueEvent).filter_by(queue_entry_id=entry.id, event_type='check_in').count() == 1
    assert db.query(models.AuditLog).filter_by(action='check_in_arrival').count() == 0


# ---------- transition ----------

def test_transition_full_lifecycle_sets_timestamps_and_appends_events(db, service_point):
    entry = qs.check_in(db, None, service_point.id, _phone(1))

    qs.transition(db, entry.id, 'called', actor='staff')
    qs.transition(db, entry.id, 'in_service', actor='staff')
    qs.transition(db, entry.id, 'done', actor='staff')

    db.refresh(entry)
    assert entry.status == 'done'
    assert entry.called_at is not None
    assert entry.service_start_at is not None
    assert entry.service_end_at is not None

    events = (db.query(models.QueueEvent)
              .filter_by(queue_entry_id=entry.id)
              .order_by(models.QueueEvent.id).all())
    # check_in + call + start_service + end_service
    assert [e.event_type for e in events] == ['check_in', 'call', 'start_service', 'end_service']
    # from/to ถูกต้อง (append-only — 4 แถว ไม่มีการแก้ของเดิม)
    assert (events[1].from_status, events[1].to_status) == ('checked_in', 'called')
    assert (events[2].from_status, events[2].to_status) == ('called', 'in_service')
    assert (events[3].from_status, events[3].to_status) == ('in_service', 'done')
    assert events[1].actor == 'staff'


@pytest.mark.parametrize("to_status,ts_field,other_fields", [
    ('called', 'called_at', ['service_start_at', 'service_end_at']),
    ('in_service', 'service_start_at', ['service_end_at']),
    ('done', 'service_end_at', []),
])
def test_transition_sets_only_the_right_timestamp(db, service_point, to_status, ts_field, other_fields):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    # เดินสถานะมาให้ถูกลำดับก่อน (เพื่อ test field ปลายทาง)
    order = ['called', 'in_service', 'done']
    for st in order[:order.index(to_status) + 1]:
        qs.transition(db, entry.id, st)
    db.refresh(entry)
    assert getattr(entry, ts_field) is not None
    for f in other_fields:
        assert getattr(entry, f) is None


def test_transition_no_show_closes_entry_with_event(db, service_point):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    qs.transition(db, entry.id, 'no_show', actor='system')
    db.refresh(entry)
    assert entry.status == 'no_show'
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id)
          .order_by(models.QueueEvent.id.desc()).first())
    assert ev.event_type == 'no_show'
    assert (ev.from_status, ev.to_status) == ('checked_in', 'no_show')


def test_transition_skip_closes_entry_with_event(db, service_point):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    qs.transition(db, entry.id, 'skipped', actor='staff')
    db.refresh(entry)
    assert entry.status == 'skipped'
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id)
          .order_by(models.QueueEvent.id.desc()).first())
    assert ev.event_type == 'skip'
    assert ev.to_status == 'skipped'


def test_sweep_no_shows_marks_checked_in_after_session_close(db, service_point):
    day = datetime.date(2026, 6, 15)
    sess = models.ServiceSession(
        service_point_id=service_point.id,
        session_date=day,
        name="08:30-12:00",
        start_time=datetime.time(8, 30),
        end_time=datetime.time(12, 0),
    )
    db.add(sess)
    db.add(models.GracePolicy(service_point_id=None, no_show_grace_min=10))
    db.commit()
    db.refresh(sess)

    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_id=sess.id,
        session_date=day,
        patient_ref="phone:+66810000901",
        entry_class='appointment',
        queue_number=1,
        status='checked_in',
        check_in_at=datetime.datetime(2026, 6, 15, 8, 45),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    n = qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 12, 11))

    assert n == 1
    db.refresh(entry)
    assert entry.status == 'no_show'
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id)
          .order_by(models.QueueEvent.id.desc()).first())
    assert ev.event_type == 'no_show'
    assert (ev.from_status, ev.to_status) == ('checked_in', 'no_show')
    assert ev.event_metadata == {'reason': 'session_closed'}


def test_sweep_no_shows_keeps_entries_before_deadline(db, service_point):
    day = datetime.date(2026, 6, 15)
    sess = models.ServiceSession(
        service_point_id=service_point.id,
        session_date=day,
        name="08:30-12:00",
        start_time=datetime.time(8, 30),
        end_time=datetime.time(12, 0),
    )
    db.add(sess)
    db.add(models.GracePolicy(service_point_id=None, no_show_grace_min=10))
    db.commit()
    db.refresh(sess)

    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_id=sess.id,
        session_date=day,
        patient_ref="phone:+66810000902",
        entry_class='appointment',
        queue_number=1,
        status='checked_in',
        check_in_at=datetime.datetime(2026, 6, 15, 8, 45),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    n = qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 12, 10))

    assert n == 0
    db.refresh(entry)
    assert entry.status == 'checked_in'
    assert db.query(models.QueueEvent).filter_by(queue_entry_id=entry.id).count() == 0


def test_sweep_no_shows_closes_stale_called_after_timeout(db, service_point):
    day = datetime.date(2026, 6, 15)
    db.add(models.QueuePolicy(service_point_id=None, call_timeout_min=5))
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=day,
        patient_ref="phone:+66810000903",
        entry_class='walkin',
        queue_number=1,
        status='called',
        check_in_at=datetime.datetime(2026, 6, 15, 8, 50),
        called_at=datetime.datetime(2026, 6, 15, 9, 0),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    n = qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 9, 6))

    assert n == 1
    db.refresh(entry)
    assert entry.status == 'no_show'
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id)
          .order_by(models.QueueEvent.id.desc()).one())
    assert ev.event_type == 'no_show'
    assert (ev.from_status, ev.to_status) == ('called', 'no_show')
    assert ev.event_metadata == {'reason': 'called_timeout', 'call_timeout_min': 5}


def test_sweep_no_shows_keeps_called_before_timeout(db, service_point):
    day = datetime.date(2026, 6, 15)
    db.add(models.QueuePolicy(service_point_id=None, call_timeout_min=5))
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=day,
        patient_ref="phone:+66810000904",
        entry_class='walkin',
        queue_number=1,
        status='called',
        check_in_at=datetime.datetime(2026, 6, 15, 8, 50),
        called_at=datetime.datetime(2026, 6, 15, 9, 0),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    n = qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 9, 5))

    assert n == 0
    db.refresh(entry)
    assert entry.status == 'called'
    assert db.query(models.QueueEvent).filter_by(queue_entry_id=entry.id).count() == 0


def test_sweep_no_shows_treats_non_positive_call_timeout_as_default(db, service_point):
    day = datetime.date(2026, 6, 15)
    db.add(models.QueuePolicy(service_point_id=None, call_timeout_min=0))
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=day,
        patient_ref="phone:+66810000905",
        entry_class='walkin',
        queue_number=1,
        status='called',
        check_in_at=datetime.datetime(2026, 6, 15, 8, 50),
        called_at=datetime.datetime(2026, 6, 15, 9, 0),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 9, 1)) == 0
    db.refresh(entry)
    assert entry.status == 'called'

    assert qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 9, 6)) == 1
    db.refresh(entry)
    assert entry.status == 'no_show'
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id)
          .order_by(models.QueueEvent.id.desc()).one())
    assert ev.event_metadata == {'reason': 'called_timeout', 'call_timeout_min': 5}


def test_transition_unknown_status_raises(db, service_point):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    with pytest.raises(ValueError):
        qs.transition(db, entry.id, 'banana')


# ---------- state machine enforcement (finding 2) ----------

@pytest.mark.parametrize("path,bad", [
    ([], 'done'),               # checked_in -> done (ข้าม)
    ([], 'in_service'),         # checked_in -> in_service (ข้าม)
    (['called'], 'called'),     # called -> called (เรียกซ้ำ)
    (['called'], 'done'),       # called -> done (ข้าม in_service)
    (['called', 'in_service', 'done'], 'called'),  # done -> called (จาก terminal)
])
def test_transition_rejects_invalid(db, service_point, path, bad):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    for st in path:
        qs.transition(db, entry.id, st)
    with pytest.raises(qs.InvalidTransition):
        qs.transition(db, entry.id, bad)
    # ยืนยันว่าไม่มี event ปลอมถูกเขียน (สถานะปัจจุบันยังเป็นตัวสุดท้ายของ path)
    db.refresh(entry)
    assert entry.status == (path[-1] if path else 'checked_in')


def test_no_called_to_called_event_ever_written(db, service_point):
    entry = qs.check_in(db, None, service_point.id, _phone(1))
    qs.transition(db, entry.id, 'called')
    with pytest.raises(qs.InvalidTransition):
        qs.transition(db, entry.id, 'called')
    bogus = (db.query(models.QueueEvent)
             .filter_by(queue_entry_id=entry.id, from_status='called', to_status='called').count())
    assert bogus == 0


# ---------- call_next: atomic FIFO ----------

def test_call_next_fifo_and_none_when_empty(make_session):
    # parallel_servers=2 เพื่อทดสอบ "ลำดับ FIFO" (เรียก 1 ก่อน 2) โดยไม่ติด capacity
    s = make_session()
    sp_id = _make_sp(s, 2)
    day = datetime.date(2026, 6, 13)
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    assert qs.call_next(s, sp_id, day) is None                # ไม่มีคิว
    qs.check_in(s, None, sp_id, _phone(1), now=now)
    qs.check_in(s, None, sp_id, _phone(2), now=now)
    e = qs.call_next(s, sp_id, day)
    assert e.queue_number == 1 and e.status == 'called'
    e2 = qs.call_next(s, sp_id, day)
    assert e2.queue_number == 2 and e2.status == 'called'     # FIFO: เรียก 1 ก่อน 2
    assert qs.call_next(s, sp_id, day) is None                # หมดคิวรอ
    s.close()


def test_call_next_capacity_blocks_and_frees(db, service_point):
    """capacity guard (single-thread): parallel_servers=1 -> เรียกได้ครั้งละ 1, ปิดแล้วค่อยเรียกถัดไป"""
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    day = datetime.date(2026, 6, 13)
    qs.check_in(db, None, service_point.id, _phone(1), now=now)
    qs.check_in(db, None, service_point.id, _phone(2), now=now)

    e1 = qs.call_next(db, service_point.id, day)
    assert e1 is not None and e1.queue_number == 1
    assert qs.call_next(db, service_point.id, day) is None      # server เต็ม (1 called)
    qs.transition(db, e1.id, 'in_service')
    assert qs.call_next(db, service_point.id, day) is None      # in_service ยังกิน server
    qs.transition(db, e1.id, 'done')
    e2 = qs.call_next(db, service_point.id, day)
    assert e2 is not None and e2.queue_number == 2             # ว่างแล้ว -> เรียกถัดไปได้


def _make_sp(s, servers):
    sp = models.ServicePoint(name="multi", sp_type='room', parallel_servers=servers)
    s.add(sp)
    s.commit()
    s.refresh(sp)
    return sp.id


@pytest.mark.parametrize("servers,checkins", [(1, 5), (3, 6)])
def test_concurrent_call_next_respects_capacity(make_session, servers, checkins):
    """กดเรียกพร้อมกันหลาย request -> เรียกได้ไม่เกิน parallel_servers, ไม่มี double-call"""
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    day = datetime.date(2026, 6, 13)
    s0 = make_session()
    sp_id = _make_sp(s0, servers)
    for i in range(checkins):
        qs.check_in(s0, None, sp_id, _phone(i), now=now)
    s0.close()

    N = checkins
    barrier = threading.Barrier(N)
    results = [None] * N
    errors = [None] * N

    def worker(i):
        s = make_session()
        try:
            barrier.wait(timeout=10)
            e = qs.call_next(s, sp_id, day)
            results[i] = e.queue_number if e else None
        except Exception as ex:  # noqa: BLE001
            errors[i] = repr(ex)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(e is None for e in errors), f"errors: {errors}"
    got = [r for r in results if r is not None]
    assert len(got) == servers, f"capacity={servers} ควรเรียกได้ {servers} แต่ได้ {sorted(got)}"
    assert len(got) == len(set(got)), f"คิวถูกเรียกซ้ำ: {sorted(got)}"
    s = make_session()
    n_called = s.query(models.QueueEntry).filter_by(service_point_id=sp_id, status='called').count()
    bogus = s.query(models.QueueEvent).filter_by(from_status='called', to_status='called').count()
    s.close()
    assert n_called == servers
    assert bogus == 0


# ---------- appointment <-> service_point / session consistency (findings 2, 6) ----------

def test_checkin_rejects_appointment_bound_to_other_service_point(db, service_point):
    other = models.ServicePoint(name="other", sp_type='room', parallel_servers=1)
    db.add(other)
    db.commit()
    db.refresh(other)
    appt = models.Appointment(
        guest_name="X",
        guest_phone=_phone(20),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
        service_point_id=other.id,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    with pytest.raises(qs.ServicePointMismatch):
        qs.check_in(db, appt.id, service_point.id, _phone(20))


def test_checkin_rejects_session_at_other_service_point(db, service_point):
    other = models.ServicePoint(name="other", sp_type='room', parallel_servers=1)
    db.add(other)
    db.commit()
    db.refresh(other)
    sess = models.ServiceSession(
        service_point_id=other.id, session_date=datetime.date(2026, 6, 13),
        name="เช้า", start_time=datetime.time(8, 30), end_time=datetime.time(12, 0),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    appt = models.Appointment(
        guest_name="Y",
        guest_phone=_phone(21),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
        session_id=sess.id,            # session ของ other -> check-in ที่ service_point ต้องถูก reject
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    with pytest.raises(qs.ServicePointMismatch):
        qs.check_in(db, appt.id, service_point.id, _phone(21))


def test_checkin_appointment_with_matching_session_succeeds(db, service_point):
    sess = models.ServiceSession(
        service_point_id=service_point.id, session_date=datetime.date(2026, 6, 13),
        name="เช้า", start_time=datetime.time(8, 30), end_time=datetime.time(12, 0),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    appt = models.Appointment(
        guest_name="Z",
        guest_phone=_phone(22),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
        session_id=sess.id, service_point_id=service_point.id,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    entry = qs.check_in(db, appt.id, service_point.id, _phone(22))
    assert entry.service_point_id == service_point.id
    assert entry.session_id == sess.id


# ---------- appointment check-in idempotency under concurrency (finding 1) ----------

def test_concurrent_appointment_checkin_is_idempotent(make_session, service_point):
    sp_id = service_point.id
    s0 = make_session()
    appt = models.Appointment(
        guest_name="นัด X",
        guest_phone=_phone(30),
        start_time=datetime.datetime(2026, 6, 13, 10, 0),
        end_time=datetime.datetime(2026, 6, 13, 10, 30),
    )
    s0.add(appt)
    s0.commit()
    s0.refresh(appt)
    appt_id = appt.id
    s0.close()

    N = 8
    barrier = threading.Barrier(N)
    results = [None] * N
    errors = [None] * N

    def worker(i):
        s = make_session()
        try:
            barrier.wait(timeout=10)
            e = qs.check_in(s, appt_id, sp_id, _phone(30))
            results[i] = e.id
        except Exception as ex:  # noqa: BLE001
            errors[i] = repr(ex)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(e is None for e in errors), f"errors: {errors}"
    assert len(set(results)) == 1, f"appointment เดียวควรได้ entry เดียว แต่ได้ {set(results)}"
    s = make_session()
    n_active = (s.query(models.QueueEntry)
                .filter(models.QueueEntry.appointment_id == appt_id,
                        models.QueueEntry.status.in_(('checked_in', 'called', 'in_service')))
                .count())
    s.close()
    assert n_active == 1, f"คาดว่ามี active entry 1 แถว แต่มี {n_active}"


def test_transition_missing_entry_raises(db, service_point):
    with pytest.raises(ValueError):
        qs.transition(db, 999999, 'called')


# ---------- concurrency ----------

def test_concurrent_checkin_no_duplicate_queue_number(make_session, service_point):
    """N thread สแกนพร้อมกันที่จุด+วันเดียวกัน -> queue_number ต้องเป็น 1..N ไม่ซ้ำ/ไม่ขาด"""
    sp_id = service_point.id
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    N = 10
    barrier = threading.Barrier(N)
    results = [None] * N
    errors = [None] * N

    def worker(i):
        s = make_session()
        try:
            barrier.wait(timeout=10)          # ให้ทุก thread เริ่มพร้อมกันสุด ๆ
            entry = qs.check_in(s, None, sp_id, _phone(i), now=now)
            results[i] = entry.queue_number
        except Exception as ex:               # noqa: BLE001
            errors[i] = repr(ex)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(e is None for e in errors), f"errors: {errors}"
    assert sorted(results) == list(range(1, N + 1)), f"duplicate/missing: {sorted(results)}"


# ---------- read helpers (FIFO call-next + count ahead) ----------

def test_next_in_line_is_fifo_among_checked_in(db, service_point):
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    e1 = qs.check_in(db, None, service_point.id, _phone(1), now=now)
    qs.check_in(db, None, service_point.id, _phone(2), now=now)
    day = datetime.date(2026, 6, 13)

    nxt = qs.next_in_line(db, service_point.id, day)
    assert nxt.id == e1.id                       # คิวเลขน้อยสุดที่ยัง checked_in

    qs.transition(db, e1.id, 'called')           # เรียก #1 ไปแล้ว -> ตกจาก checked_in
    nxt2 = qs.next_in_line(db, service_point.id, day)
    assert nxt2.queue_number == 2                # ตัวถัดไป


def test_next_in_line_none_when_empty(db, service_point):
    assert qs.next_in_line(db, service_point.id, datetime.date(2026, 6, 13)) is None


def test_count_ahead_counts_only_active_earlier_numbers(db, service_point):
    now = datetime.datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    e1 = qs.check_in(db, None, service_point.id, _phone(1), now=now)
    qs.check_in(db, None, service_point.id, _phone(2), now=now)
    e3 = qs.check_in(db, None, service_point.id, _phone(3), now=now)
    day = datetime.date(2026, 6, 13)

    assert qs.count_ahead(db, service_point.id, day, e3.queue_number) == 2

    # เดิน #1 ไป done ตาม state machine (checked_in -> called -> in_service -> done)
    qs.transition(db, e1.id, 'called')
    qs.transition(db, e1.id, 'in_service')
    qs.transition(db, e1.id, 'done')             # #1 เสร็จ -> ไม่นับเป็นคิวก่อนหน้าอีก
    assert qs.count_ahead(db, service_point.id, day, e3.queue_number) == 1
    assert qs.count_ahead(db, service_point.id, day, e1.queue_number) == 0


# ---------- arrived_ack (Patch 21 §4.4) ----------

def _called_entry(db, service_point, number=1, status='called'):
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=datetime.date(2026, 6, 15),
        patient_ref=f"phone:+6681000{number:04d}",
        entry_class='walkin',
        queue_number=number,
        status=status,
        check_in_at=datetime.datetime(2026, 6, 15, 8, 50),
        called_at=datetime.datetime(2026, 6, 15, 9, 0) if status != 'checked_in' else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@pytest.mark.parametrize("actor", ['patient', 'staff'])
def test_record_arrived_ack_sets_timestamp_and_event(db, service_point, actor):
    entry = _called_entry(db, service_point)
    now = datetime.datetime(2026, 6, 15, 9, 2, tzinfo=UTC)

    out = qs.record_arrived_ack(db, entry.id, actor=actor, now=now)

    assert out is not None and out.arrived_ack_at is not None
    assert out.status == 'called'                 # ack ไม่เปลี่ยน status (ไม่ใช่ gate)
    ev = (db.query(models.QueueEvent)
          .filter_by(queue_entry_id=entry.id, event_type='arrived_ack').one())
    assert ev.actor == actor
    assert (ev.from_status, ev.to_status) == ('called', 'called')


def test_record_arrived_ack_is_idempotent(db, service_point):
    entry = _called_entry(db, service_point)
    qs.record_arrived_ack(db, entry.id, actor='patient')
    qs.record_arrived_ack(db, entry.id, actor='patient')      # กดซ้ำ
    assert db.query(models.QueueEvent).filter_by(
        queue_entry_id=entry.id, event_type='arrived_ack').count() == 1


def test_record_arrived_ack_noop_on_closed_entry(db, service_point):
    entry = _called_entry(db, service_point, status='called')
    qs.transition(db, entry.id, 'no_show')
    assert qs.record_arrived_ack(db, entry.id, actor='staff') is None
    db.refresh(entry)
    assert entry.arrived_ack_at is None


def test_sweep_excludes_arrived_ack_called(db, service_point):
    db.add(models.QueuePolicy(service_point_id=None, call_timeout_min=5))
    db.commit()
    acked = _called_entry(db, service_point, number=1)
    stale = _called_entry(db, service_point, number=2)
    qs.record_arrived_ack(db, acked.id, actor='patient',
                          now=datetime.datetime(2026, 6, 15, 9, 1))

    # both are well past the 5-min call timeout, but the acked one must survive
    n = qs.sweep_no_shows(db, now=datetime.datetime(2026, 6, 15, 9, 30))

    assert n == 1
    db.refresh(acked); db.refresh(stale)
    assert acked.status == 'called'              # arrived -> not closed
    assert stale.status == 'no_show'
