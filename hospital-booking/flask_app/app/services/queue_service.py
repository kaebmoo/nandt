"""
Queue state machine + check-in service (Phase 1).

Flask-first: business logic ของคิวอยู่ที่นี่ (Python) — ไม่ผลักไป JS.

ฟังก์ชันรับ `db` (SQLAlchemy Session) ที่ "ผูก tenant แล้ว" ด้วย database.bind_tenant(db, schema):
- Flask: middleware ผูก g.db ให้อัตโนมัติ
- background job / test: ต้องเรียก bind_tenant(session, schema) เองก่อนใช้
เมื่อผูกแล้ว event after_begin (database.py) จะ SET search_path ให้ "ทุก transaction" ของ session
รวม transaction ใหม่หลัง commit/rollback ที่หยิบ connection ใหม่จาก pool — service จึง commit/rollback
ได้ตรง ๆ ไม่ต้อง re-SET search_path เอง

กฎที่รักษา (แผนส่วน 0 + 5):
- queue_events append-only: ทุก status change ต้อง insert event 1 แถว (ห้าม update/delete event)
- update queue_entry + insert event อยู่ใน transaction เดียว; บังคับ state machine (_ALLOWED_TRANSITIONS)
- queue_number atomic ต่อ (service_point_id, session_date) ด้วย advisory xact lock — ไม่ใช่ MAX()+1 เปล่า ๆ
- call_next เคารพ capacity (parallel_servers) + serialize ต่อ service_point กันเรียกเกิน
"""

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from shared_db import models
from . import grace_service
from . import identity_service

# โปรเจกต์ใช้เวลาไทยเป็นหลัก (แผน) — "วันนี้" ของคิว = วันตามเวลา Asia/Bangkok
BANGKOK = ZoneInfo("Asia/Bangkok")

# event_type + timestamp field ตาม to_status (ตาม 5.1)
_EVENT_TYPE_BY_STATUS = {
    'checked_in': 'check_in',
    'called': 'call',
    'in_service': 'start_service',
    'done': 'end_service',
    'no_show': 'no_show',
    'skipped': 'skip',
}
_TIMESTAMP_FIELD_BY_STATUS = {
    'called': 'called_at',
    'in_service': 'service_start_at',
    'done': 'service_end_at',
}
# สถานะที่ยัง "ไม่ปิด" (ใช้กัน check-in ซ้ำของ appointment เดิม)
_ACTIVE_STATUSES = ('checked_in', 'called', 'in_service')

# state machine: from_status -> set ของ to_status ที่อนุญาต (ตาม flow แผน 3.2)
# บังคับลำดับสถานะให้ถูก — กัน POST ตรงไป done/เรียกซ้ำ called->called ฯลฯ
_ALLOWED_TRANSITIONS = {
    'checked_in': {'called', 'no_show', 'skipped'},
    'called':     {'in_service', 'no_show', 'skipped'},
    'in_service': {'done'},
    'done':       set(),   # terminal
    'no_show':    set(),   # terminal
    'skipped':    set(),   # terminal
}


class InvalidTransition(ValueError):
    """พยายามเปลี่ยนสถานะที่ไม่อนุญาตตาม state machine (เช่น called -> called, checked_in -> done)"""


class ServicePointMismatch(ValueError):
    """check-in นัดที่ผูกกับ service_point/session อื่น มาที่จุดบริการนี้ (สแกน QR ผิดจุด)"""


@dataclass(frozen=True)
class ArrivalCheckInResult:
    """ผลลัพธ์ check-in สำหรับบริการที่ไม่เข้าคิว: บันทึก arrival แล้ว แต่ไม่มี queue entry/number"""

    appointment_id: int
    service_point_id: int
    patient_ref: str
    arrived_at: datetime.datetime
    booking_reference: str | None = None
    requires_queue: bool = False
    queue_number: None = None


def _now() -> datetime.datetime:
    """เวลาปัจจุบัน (tz-aware, Asia/Bangkok) — เก็บลง timestamptz ได้ตรง + .date() = วันไทย"""
    return datetime.datetime.now(BANGKOK)


def today() -> datetime.date:
    """วันที่ "วันนี้" ตามเวลาไทย (ใช้กับ session_date ของ walk-in + การ query คิววันนี้)"""
    return _now().date()


def record_event(db, entry, event_type, from_status, to_status,
                 actor='system', metadata=None) -> None:
    """insert queue_events 1 แถว (append-only). entry ต้อง flush แล้ว (มี id)"""
    db.add(models.QueueEvent(
        queue_entry_id=entry.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        event_metadata=metadata,
    ))


def _appointment_requires_queue(appointment) -> bool:
    """A1 gate: event_type.requires_queue ตัดสินว่านัดนี้เข้าคิวหรือไม่.

    Appointment legacy/test บางตัวไม่มี event_type_id; กรณีนั้นคง behavior เดิมให้เข้าคิว
    เพื่อไม่ทำลาย path walk-in/legacy ที่ยังไม่มีข้อมูล event type ครบ.
    """
    event_type = getattr(appointment, 'event_type', None)
    if appointment.event_type_id is None or event_type is None:
        return True
    return bool(event_type.requires_queue)


def _record_arrival_only(db, appointment, service_point_id, patient_ref, now):
    """บันทึกการมาถึงสำหรับนัด 1:1 ที่ไม่ใช้คิว โดยไม่สร้าง queue_entries/queue_events"""
    result = ArrivalCheckInResult(
        appointment_id=appointment.id,
        service_point_id=service_point_id,
        patient_ref=patient_ref,
        arrived_at=now,
        booking_reference=appointment.booking_reference,
    )
    db.add(models.AuditLog(
        action='check_in_arrival',
        resource_type='Appointment',
        resource_id=str(appointment.id),
        details={
            'service_point_id': service_point_id,
            'patient_ref': patient_ref,
            'booking_reference': appointment.booking_reference,
            'arrived_at': now.isoformat(),
            'requires_queue': False,
        },
    ))
    db.commit()
    return result


def _apply_transition(db, entry, to_status, actor, metadata=None) -> None:
    """ตรวจ state machine + set status/timestamp + insert event (ยังไม่ commit)

    entry ต้องถูก lock (FOR UPDATE) มาแล้วโดย caller เพื่อกัน transition ชนกัน
    """
    if to_status not in _EVENT_TYPE_BY_STATUS:
        raise ValueError(f"unknown to_status: {to_status!r}")
    from_status = entry.status
    if to_status not in _ALLOWED_TRANSITIONS.get(from_status, set()):
        raise InvalidTransition(
            f"transition ไม่อนุญาต: {from_status} -> {to_status} (entry {entry.id})")

    ts_field = _TIMESTAMP_FIELD_BY_STATUS.get(to_status)
    if ts_field is not None:
        setattr(entry, ts_field, _now())
    entry.status = to_status
    db.flush()
    record_event(db, entry, _EVENT_TYPE_BY_STATUS[to_status],
                 from_status, to_status, actor=actor, metadata=metadata)


def transition(db, entry_id, to_status, actor='system', metadata=None) -> None:
    """เปลี่ยนสถานะ queue_entry + เขียน queue_events 1 แถว + set timestamp ที่เกี่ยวข้อง (5.1)

    - to_status='called'     -> set called_at
    - to_status='in_service' -> set service_start_at
    - to_status='done'       -> set service_end_at
    - to_status='no_show'/'skipped' -> ปิด entry (ไม่มี timestamp เพิ่ม)
    บังคับ state machine (_ALLOWED_TRANSITIONS) — transition ไม่ถูกต้องจะ raise InvalidTransition
    update entry + insert event อยู่ transaction เดียว; ห้ามลืม insert queue_events
    """
    entry = (db.query(models.QueueEntry)
             .filter(models.QueueEntry.id == entry_id)
             .with_for_update()                     # lock เพื่อกัน transition ชนกันของ entry เดียว
             .one_or_none())
    if entry is None:
        raise ValueError(f"queue_entry {entry_id} not found")

    _apply_transition(db, entry, to_status, actor, metadata)
    db.commit()   # after_begin (database.py) จัดการ search_path ของ transaction ถัดไปให้เอง


# สถานะที่รับ arrived_ack ได้ (ยัง active) — ack เป็น signal ไม่ใช่ status/gate
_ACK_ELIGIBLE_STATUSES = ('checked_in', 'called', 'in_service')


def record_arrived_ack(db, entry_id, actor='patient', now=None):
    """บันทึก "ถึงหน้าห้องแล้ว" (Patch 21 §4.4): set arrived_ack_at + queue_events('arrived_ack').

    ไม่ใช่ status ใหม่ ไม่ใช่ gate — เป็น signal ให้ close_stale_called ยกเว้น entry นี้
    (คนมาถึงแล้วต้องไม่ถูกปิดเป็น no_show) + ให้ staff เห็น badge "ถึงแล้ว".
    actor = 'patient' (กดเองที่ status page) หรือ 'staff' (กดแทนที่ console).
    idempotent: ถ้า ack ไปแล้วคืน entry เดิมโดยไม่เขียน event ซ้ำ;
    คืน None ถ้า entry ปิดไปแล้ว (ack ไม่มีผล).
    """
    now = now or _now()
    entry = (db.query(models.QueueEntry)
             .filter(models.QueueEntry.id == entry_id)
             .with_for_update()
             .one_or_none())
    if entry is None:
        raise ValueError(f"queue_entry {entry_id} not found")
    if entry.arrived_ack_at is not None:
        db.commit()
        db.refresh(entry)
        return entry                       # idempotent — ไม่เขียน event ซ้ำ
    if entry.status not in _ACK_ELIGIBLE_STATUSES:
        db.commit()
        return None                        # entry ปิดแล้ว — ack ไม่มีผล
    entry.arrived_ack_at = now
    db.flush()
    record_event(db, entry, 'arrived_ack', entry.status, entry.status,
                 actor=actor, metadata={'arrived_ack': True})
    db.commit()
    db.refresh(entry)
    return entry


def _naive_local(dt):
    """normalize datetime ให้เป็น naive local สำหรับเทียบกับเวลาจาก DB ที่เป็น local naive"""
    if dt is not None and getattr(dt, 'tzinfo', None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _no_show_deadline(entry, grace_minutes):
    """deadline ที่ entry checked_in ควรถูกปิดเป็น no_show.

    window/session booking ใช้ session.end_time; exact appointment ที่ไม่มี session ใช้ appointment.end_time.
    walk-in ที่ไม่มี session/appointment ไม่มีเวลาปิดที่ reliable จึงไม่ sweep อัตโนมัติ
    """
    if entry.service_session is not None:
        base = datetime.datetime.combine(entry.session_date, entry.service_session.end_time)
    elif entry.appointment is not None and entry.appointment.end_time is not None:
        base = _naive_local(entry.appointment.end_time)
    else:
        return None
    return base + datetime.timedelta(minutes=grace_minutes)


def _queue_policy_for(db, service_point_id):
    pol = (db.query(models.QueuePolicy)
           .filter(models.QueuePolicy.service_point_id == service_point_id)
           .first())
    if pol is None:
        pol = (db.query(models.QueuePolicy)
               .filter(models.QueuePolicy.service_point_id.is_(None))
               .first())
    return pol


def _call_timeout_minutes(db, service_point_id, policy_cache):
    if service_point_id not in policy_cache:
        pol = _queue_policy_for(db, service_point_id)
        raw_value = pol.call_timeout_min if pol is not None else None
        try:
            timeout_min = int(raw_value) if raw_value is not None else 5
        except (TypeError, ValueError):
            timeout_min = 5
        policy_cache[service_point_id] = timeout_min if timeout_min > 0 else 5
    return policy_cache[service_point_id]


def close_stale_called(db, service_point_id=None, session_date=None,
                       now=None, actor='system', commit=True) -> int:
    """Close called entries that exceeded queue_policy.call_timeout_min.

    This returns server capacity by moving stale called entries to no_show and
    appending queue_events via the normal state machine. When used as call_next
    preflight, pass commit=False so the caller's transaction/advisory lock owns
    both cleanup and capacity calculation.
    """
    now_n = _naive_local(now or _now())
    policy_cache = {}
    count = 0

    # arrived_ack: คนยืนยันว่าถึงหน้าห้องแล้ว ห้ามปิดเป็น stale/no_show (Patch 21 §4.4)
    query = (db.query(models.QueueEntry)
             .filter(models.QueueEntry.status == 'called',
                     models.QueueEntry.arrived_ack_at.is_(None)))
    if service_point_id is not None:
        query = query.filter(models.QueueEntry.service_point_id == service_point_id)
    if session_date is not None:
        query = query.filter(models.QueueEntry.session_date == session_date)

    for entry in query.with_for_update().all():
        if entry.called_at is None:
            continue
        timeout_min = _call_timeout_minutes(db, entry.service_point_id, policy_cache)
        deadline = _naive_local(entry.called_at) + datetime.timedelta(minutes=timeout_min)
        if now_n > deadline:
            _apply_transition(
                db,
                entry,
                'no_show',
                actor,
                metadata={'reason': 'called_timeout', 'call_timeout_min': timeout_min},
            )
            count += 1

    if commit:
        db.commit()
    return count


def sweep_no_shows(db, now=None, actor='system') -> int:
    """Phase 2.5: ปิด checked_in/called stale เป็น no_show + queue_events('no_show').

    ทำงานต่อ tenant บน session ที่ bind_tenant แล้ว. ใช้ transaction เดียวครอบ entries ทั้งหมด
    และใช้ _apply_transition เพื่อรักษา state machine + append-only event log.
    """
    now_n = _naive_local(now or _now())
    policy_cache = {}
    count = 0

    entries = (db.query(models.QueueEntry)
               .filter(models.QueueEntry.status == 'checked_in')
               .with_for_update()
               .all())
    for entry in entries:
        if entry.service_point_id not in policy_cache:
            pol = grace_service.get_grace_policy(db, entry.service_point_id)
            policy_cache[entry.service_point_id] = (
                pol.no_show_grace_min if pol is not None and pol.no_show_grace_min is not None else 10
            )
        deadline = _no_show_deadline(entry, policy_cache[entry.service_point_id])
        if deadline is not None and now_n > deadline:
            _apply_transition(db, entry, 'no_show', actor, metadata={'reason': 'session_closed'})
            count += 1

    count += close_stale_called(db, now=now_n, actor=actor, commit=False)
    db.commit()
    return count


def call_next(db, service_point_id, session_date, actor='staff') -> "models.QueueEntry | None":
    """เลือก + เรียกคิวถัดไปแบบ atomic (Phase 1 = FIFO) + เคารพ capacity ของ service_point

    - serialize call_next ต่อ service_point ด้วย advisory xact lock -> เจ้าหน้าที่กดพร้อมกัน/
      ดับเบิลคลิก ไม่เรียกเกินจำนวน server (กัน parallel_servers=1 ถูกเรียก 2 คิวพร้อมกัน)
    - capacity guard: ถ้า outstanding (called + in_service) >= parallel_servers -> ไม่เรียกเพิ่ม
    - เลือก checked_in ที่ queue_number น้อยสุด (FOR UPDATE SKIP LOCKED) แล้ว transition('called')
      ทั้งหมดอยู่ transaction เดียว

    Phase 2.3 จะแทน selection ด้วย priority_service.call_next() (ratio/score + grace eligibility)
    คืน entry ที่ถูกเรียก หรือ None (ไม่มีคิวรอ / server เต็ม)
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock("
             "hashtextextended(current_schema() || ':call:' || :sp, 0))"),
        {"sp": int(service_point_id)},
    )
    sp = db.query(models.ServicePoint).filter_by(id=service_point_id).one_or_none()
    servers = sp.parallel_servers if (sp and sp.parallel_servers) else 1
    close_stale_called(
        db,
        service_point_id=service_point_id,
        session_date=session_date,
        actor='system',
        commit=False,
    )
    outstanding = (db.query(models.QueueEntry)
                   .filter(models.QueueEntry.service_point_id == service_point_id,
                           models.QueueEntry.session_date == session_date,
                           models.QueueEntry.status.in_(('called', 'in_service')))
                   .count())

    entry = None
    if outstanding < servers:
        entry = (db.query(models.QueueEntry)
                 .filter(models.QueueEntry.service_point_id == service_point_id,
                         models.QueueEntry.session_date == session_date,
                         models.QueueEntry.status == 'checked_in')
                 .order_by(models.QueueEntry.queue_number.asc())
                 .with_for_update(skip_locked=True)
                 .first())
        if entry is not None:
            _apply_transition(db, entry, 'called', actor)

    db.commit()   # commit เสมอ -> ปล่อย advisory lock (+ persist ถ้ามีการเรียก)
    if entry is not None:
        db.refresh(entry)
    return entry


def check_in(db, appointment_id, service_point_id, patient_ref,
             now=None) -> "models.QueueEntry | ArrivalCheckInResult":
    """check-in -> สร้าง queue_entry (status='checked_in') + queue_events('check_in') (5.2)

    - walk-in (appointment_id=None) -> entry_class='walkin'
    - appointment -> entry_class='appointment' (Phase 1 = priority เต็ม;
      Phase 2.2 จะแทรก grace_service.classify_on_checkin() ตรงจุดที่มาร์กไว้)
    - queue_number = running atomic ต่อ (service_point_id, session_date)
    - idempotent: ถ้า appointment นี้ check-in ไปแล้วและยัง active -> คืน entry เดิม (กันสแกน QR ซ้ำ)
    """
    now = now or _now()
    entry_class = 'walkin'
    session_id = None
    session_date = now.date()
    canonical_ref = None

    if appointment_id is not None:
        appointment = (db.query(models.Appointment)
                       .filter(models.Appointment.id == appointment_id)
                       .one_or_none())
        if appointment is None:
            raise ValueError(f"appointment {appointment_id} not found")
        canonical_ref = identity_service.resolve_patient_ref(
            appointment=appointment,
            fallback_ref=patient_ref,
            required=True,
        )
        # นัดต้องตรงกับจุดบริการที่ check-in — กันสแกน QR ผิดจุด และกันไม่ให้ entry.session_id
        # ชี้ session ของคนละจุดกับ entry.service_point_id (จะ inconsistent ทันทีใน Phase 1B)
        if appointment.service_point_id is not None and appointment.service_point_id != service_point_id:
            raise ServicePointMismatch(
                f"appointment {appointment_id} ผูกกับ service_point {appointment.service_point_id}, "
                f"ไม่ใช่ {service_point_id}")
        sess = None
        if appointment.session_id is not None:
            sess = (db.query(models.ServiceSession)
                    .filter_by(id=appointment.session_id).one_or_none())
            if sess is not None and sess.service_point_id != service_point_id:
                raise ServicePointMismatch(
                    f"session {appointment.session_id} ของนัดอยู่ที่ service_point "
                    f"{sess.service_point_id}, ไม่ใช่ {service_point_id}")
        if not _appointment_requires_queue(appointment):
            return _record_arrival_only(db, appointment, service_point_id, canonical_ref, now)
        # Phase 2.2: grace rule — มาตรงเวลา → 'appointment', มาสายเกินช่วง → demote ('walkin'),
        # require_rebook → NoShowError (ไม่รับเข้าคิว). early ไม่ถูกลงโทษ (ดู grace_service §5.3)
        policy = grace_service.get_grace_policy(db, service_point_id)
        if policy is not None:
            entry_class = grace_service.classify_on_checkin(appointment, now, policy, session=sess)
        else:
            entry_class = 'appointment'   # ไม่มี policy → priority เต็ม (เดิม)
        session_id = appointment.session_id
        if appointment.start_time is not None:
            session_date = appointment.start_time.date()

        # lock ต่อ appointment (ครอบทุก service_point) เพื่อ serialize check-in ของ
        # appointment เดียวกัน — กัน race ที่สแกน QR เดิมพร้อมกัน (รวมถึงข้าม service_point
        # ซึ่ง lock (sp,date) ด้านล่างครอบไม่ถึง). ลำดับ lock เสมอ: appt ก่อน sp -> ไม่ deadlock
        db.execute(
            text("SELECT pg_advisory_xact_lock("
                 "hashtextextended(current_schema() || ':appt:' || :aid, 0))"),
            {"aid": int(appointment_id)},
        )
        # re-check "ภายใน lock" (READ COMMITTED เห็น commit ล่าสุด) -> idempotent จริง
        existing = (db.query(models.QueueEntry)
                    .filter(models.QueueEntry.appointment_id == appointment_id,
                            models.QueueEntry.status.in_(_ACTIVE_STATUSES))
                    .first())
        if existing is not None:
            # ปิด transaction ก่อน return เพื่อปล่อย advisory appt-lock ทันที (ไม่ถือค้างจน teardown)
            # after_begin จะ SET search_path ให้ transaction ถัดไป (รวม refresh) เพราะ session bound แล้ว
            db.commit()
            db.refresh(existing)
            return existing   # active check-in มีอยู่แล้ว — idempotent
    else:
        canonical_ref = identity_service.resolve_patient_ref(
            fallback_ref=patient_ref,
            required=True,
        )

    # --- atomic queue_number ---
    # advisory xact lock ต่อ (schema, service_point, date): serialize concurrent check-in
    # ของจุด+วันเดียวกัน lock ปล่อยอัตโนมัติตอน commit. ใช้ current_schema() ใน key เพื่อ
    # ไม่ให้ tenant ต่างกันแย่ง lock กัน (advisory lock เป็น database-global)
    db.execute(
        text("SELECT pg_advisory_xact_lock("
             "hashtextextended(current_schema() || ':' || :sp || ':' || :d, 0))"),
        {"sp": int(service_point_id), "d": session_date.isoformat()},
    )
    next_no = db.execute(
        text("SELECT COALESCE(MAX(queue_number), 0) + 1 FROM queue_entries "
             "WHERE service_point_id = :sp AND session_date = :d"),
        {"sp": int(service_point_id), "d": session_date},
    ).scalar()

    entry = models.QueueEntry(
        appointment_id=appointment_id,
        service_point_id=service_point_id,
        session_id=session_id,
        session_date=session_date,
        patient_ref=canonical_ref,
        entry_class=entry_class,
        queue_number=next_no,
        status='checked_in',
        check_in_at=now,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        # DB backstop: partial unique index uq_queue_active_appointment ยิง
        # (ปกติ appt-lock + re-check กันได้หมดแล้ว — ตรงนี้เผื่อ path อื่น/edge เท่านั้น)
        # rollback ย้อน search_path กลับ แต่ transaction ถัดไปจะถูก SET ให้เองโดย after_begin
        db.rollback()
        if appointment_id is not None:
            existing = (db.query(models.QueueEntry)
                        .filter(models.QueueEntry.appointment_id == appointment_id,
                                models.QueueEntry.status.in_(_ACTIVE_STATUSES))
                        .first())
            if existing is not None:
                return existing
        raise
    record_event(db, entry, 'check_in', None, 'checked_in', actor='patient',
                 metadata={'queue_number': next_no, 'entry_class': entry_class})
    # Phase 2.2: นัดที่ถูก grace demote เป็น walk-in → เขียน event 'reclass' (append-only, ขับ analytics)
    if appointment_id is not None and entry_class == 'walkin':
        record_event(db, entry, 'reclass', 'checked_in', 'checked_in', actor='system',
                     metadata={'from_class': 'appointment', 'to_class': 'walkin', 'reason': 'late'})
    db.commit()
    db.refresh(entry)            # transaction ใหม่หลัง commit -> after_begin SET search_path ให้แล้ว
    return entry


# --- read helpers (สำหรับ console / display / ticket) ---

def next_in_line(db, service_point_id, session_date):
    """Phase 1: FIFO — entry สถานะ checked_in ที่ queue_number น้อยสุดของ (จุด, วัน)

    Phase 2.3 จะแทนที่ด้วย priority_service.call_next() (ratio/score + grace eligibility)
    """
    return (db.query(models.QueueEntry)
            .filter(models.QueueEntry.service_point_id == service_point_id,
                    models.QueueEntry.session_date == session_date,
                    models.QueueEntry.status == 'checked_in')
            .order_by(models.QueueEntry.queue_number.asc())
            .first())


def count_ahead(db, service_point_id, session_date, queue_number):
    """จำนวนคิวที่ยัง active (checked_in/called/in_service) และมาก่อน (queue_number น้อยกว่า)

    ใช้โดย wait estimator และหน้า ticket เพื่อแสดงจำนวนคิวก่อนหน้า
    """
    return (db.query(models.QueueEntry)
            .filter(models.QueueEntry.service_point_id == service_point_id,
                    models.QueueEntry.session_date == session_date,
                    models.QueueEntry.status.in_(('checked_in', 'called', 'in_service')),
                    models.QueueEntry.queue_number < queue_number)
            .count())
