"""Queue priority engine (§5.4) — เลือก "คิวถัดไป" อย่างเป็นธรรม: นัด vs walk-in สลับกัน + กันรอจนลืม

แทน FIFO เดิม (queue_service.call_next) ด้วย:
- **capacity guard**: outstanding = นับ called + in_service (คน 'called' กินช่องอยู่) เทียบ parallel_servers
- **eligibility**: walk-in eligible เสมอ; appointment eligible เมื่อ now >= slot_start - appointment_early_eligible_minutes
- **starvation guard** (ทุก mode): walk-in ที่รอ > walkin_max_wait_minutes ถูกดันขึ้นก่อน
- **ratio interleaving** (mode='ratio'): เรียกนัดติดกันครบ appointment_to_walkin_ratio แล้วมี walk-in รอ → แทรก walk-in
- mode='score' → Phase 2.4 (compute_priority_score)

concurrency: serialize call_next ต่อ service_point ด้วย advisory xact lock (เหมือน queue_service) แล้ว
re-fetch entry ที่เลือกด้วย FOR UPDATE + re-check 'checked_in' ก่อน transition (กันชนกับ transition อื่น)

เวลาทั้งหมด normalize เป็น naive (เทียบกับเวลานัด naive local); ห้ามคำนวณ wait แบบ inline (Phase 3 ใช้ estimator)
"""

import datetime

from sqlalchemy import text

from shared_db import models
from . import queue_service as qs


def get_queue_policy(db, service_point_id):
    """queue_policy ของ service_point (ถ้ามี) ไม่งั้น default ของ tenant (service_point_id IS NULL)"""
    pol = (db.query(models.QueuePolicy)
           .filter(models.QueuePolicy.service_point_id == service_point_id)
           .first())
    if pol is None:
        pol = (db.query(models.QueuePolicy)
               .filter(models.QueuePolicy.service_point_id.is_(None))
               .first())
    return pol


def _default_policy():
    """fallback policy สำหรับ tenant เก่าที่ยังไม่มี row default (กัน staff console หยุดเรียกคิว)"""
    return models.QueuePolicy(
        service_point_id=None,
        mode='ratio',
        appointment_to_walkin_ratio=3,
        walkin_max_wait_minutes=45,
        appointment_early_eligible_minutes=15,
        call_timeout_min=5,
        w_class=100,
        w_wait=1,
        w_window=2,
    )


def _naive(dt):
    if dt is not None and getattr(dt, 'tzinfo', None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _appt_slot_start(entry):
    """เวลาเริ่ม slot ของ appointment entry (naive) — window=session, exact=appt.start_time; None=คำนวณไม่ได้"""
    appt = entry.appointment
    if appt is None or appt.start_time is None:
        return None
    if appt.session_id is not None and entry.service_session is not None:
        on_date = _naive(appt.start_time).date()
        return datetime.datetime.combine(on_date, entry.service_session.start_time)
    return _naive(appt.start_time)


def _appt_slot_end(entry):
    """เวลาจบ slot ของ appointment entry (naive) — window=session, exact=appt.end_time; None=คำนวณไม่ได้"""
    appt = entry.appointment
    if appt is None:
        return None
    if appt.session_id is not None and entry.service_session is not None and appt.start_time is not None:
        on_date = _naive(appt.start_time).date()
        return datetime.datetime.combine(on_date, entry.service_session.end_time)
    return _naive(appt.end_time)


def _appt_eligible(entry, now_naive, policy) -> bool:
    """appointment เรียกได้เมื่อ now ถึง slot_start - early_eligible แล้ว (กันเรียกนัดบ่ายมาตอนเช้า)"""
    ss = _appt_slot_start(entry)
    if ss is None:
        return True   # ไม่มีเวลา → ให้เรียกได้ (ไม่กั๊ก)
    earliest = ss - datetime.timedelta(minutes=policy.appointment_early_eligible_minutes)
    return now_naive >= earliest


def _minutes_waited(entry, now_naive) -> float:
    ci = _naive(entry.check_in_at)
    if ci is None:
        return 0.0
    return max(0.0, (now_naive - ci).total_seconds() / 60.0)


def _window_proximity(entry, now_naive) -> float:
    """คะแนนความใกล้ slot สำหรับ score mode.

    - อยู่ใน window แล้ว = 1.0
    - ก่อนเริ่มไม่เกิน 60 นาที = ไล่จาก 0..1
    - เลย window แล้ว = 0.5 (ยังให้คะแนนบ้าง แต่ late demote ควรถูกจัดใน grace แล้ว)
    """
    if entry.entry_class != 'appointment':
        return 0.0
    start = _appt_slot_start(entry)
    if start is None:
        return 0.0
    end = _appt_slot_end(entry)
    if end is not None and start <= now_naive <= end:
        return 1.0
    if now_naive < start:
        minutes_until = (start - now_naive).total_seconds() / 60.0
        return max(0.0, 1.0 - (minutes_until / 60.0))
    return 0.5


def compute_priority_score(entry, policy, now) -> float:
    """คำนวณ priority score ตามแผน §5.4 สำหรับ mode='score'.

    class_rank ให้ appointment มากกว่า walk-in โดย default แต่ w_wait ทำให้ walk-in ที่รอนานมาก
    แซงได้ในที่สุด. Starvation guard ยังเป็น hard override ก่อน score ใน call_next().
    """
    now_naive = _naive(now)
    class_rank = 2.0 if entry.entry_class == 'appointment' else 1.0
    minutes_waited = _minutes_waited(entry, now_naive)
    window_proximity = _window_proximity(entry, now_naive)
    return (
        float(policy.w_class) * class_rank
        + float(policy.w_wait) * minutes_waited
        + float(policy.w_window) * window_proximity
    )


def _recent_appt_streak(db, service_point_id, session_date) -> int:
    """จำนวนครั้งที่ "เรียกนัด" ติดกันล่าสุดของ (จุด, วัน) — ใช้คุม ratio interleaving

    ดูจาก entries ที่ถูกเรียกแล้ว (called_at ไม่ null) เรียงล่าสุดก่อน นับ entry_class='appointment' ที่ติดกัน
    (entry ที่ถูก grace demote = entry_class 'walkin' → ตัด streak เหมือน walk-in จริง)
    """
    recent = (db.query(models.QueueEntry)
              .filter(models.QueueEntry.service_point_id == service_point_id,
                      models.QueueEntry.session_date == session_date,
                      models.QueueEntry.called_at.isnot(None))
              .order_by(models.QueueEntry.called_at.desc(), models.QueueEntry.id.desc())
              .all())
    streak = 0
    for e in recent:
        if e.entry_class == 'appointment':
            streak += 1
        else:
            break
    return streak


def _select(db, service_point_id, session_date, elig_appts, walkins, now_naive, policy):
    """เลือก entry ที่ควรเรียกถัดไป (ยังไม่ transition) — None ถ้าไม่มีใครให้เรียก"""
    # 1) starvation guard: walk-in ที่รอนานเกิน threshold → ดันขึ้นก่อน (คนรอนานสุดก่อน)
    starving = [w for w in walkins if _minutes_waited(w, now_naive) > policy.walkin_max_wait_minutes]
    if starving:
        return min(starving, key=lambda w: w.queue_number)

    if policy.mode == 'score':
        candidates = elig_appts + walkins
        if candidates:
            return max(candidates, key=lambda e: (compute_priority_score(e, policy, now_naive), -e.queue_number))
        return None

    # 2) ratio interleaving: เรียกนัดติดกันครบ ratio แล้ว + มี walk-in รอ → แทรก walk-in
    if walkins and _recent_appt_streak(db, service_point_id, session_date) >= policy.appointment_to_walkin_ratio:
        return min(walkins, key=lambda w: w.queue_number)

    # 3) ปกติ: เรียก appointment ที่ eligible + slot ใกล้สุดก่อน
    if elig_appts:
        return min(elig_appts, key=lambda a: (_appt_slot_start(a) or datetime.datetime.max, a.queue_number))

    # 4) ไม่มี appointment eligible → เรียก walk-in (FIFO) ถ้ามี (กัน server ว่าง)
    if walkins:
        return min(walkins, key=lambda w: w.queue_number)
    return None


def call_next(db, service_point_id, session_date, now=None, actor='staff'):
    """เลือก + เรียกคิวถัดไปแบบ atomic (ratio + starvation + eligibility + capacity) — คืน entry หรือ None"""
    now_naive = _naive(now or qs._now())

    # serialize call_next ต่อ service_point (เหมือน queue_service.call_next)
    db.execute(
        text("SELECT pg_advisory_xact_lock("
             "hashtextextended(current_schema() || ':call:' || :sp, 0))"),
        {"sp": int(service_point_id)},
    )

    sp = db.query(models.ServicePoint).filter_by(id=service_point_id).one_or_none()
    servers = sp.parallel_servers if (sp and sp.parallel_servers) else 1
    policy = get_queue_policy(db, service_point_id) or _default_policy()
    qs.close_stale_called(
        db,
        service_point_id=service_point_id,
        session_date=session_date,
        now=now_naive,
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
        candidates = (db.query(models.QueueEntry)
                      .filter(models.QueueEntry.service_point_id == service_point_id,
                              models.QueueEntry.session_date == session_date,
                              models.QueueEntry.status == 'checked_in')
                      .all())
        elig_appts = [c for c in candidates
                      if c.entry_class == 'appointment' and _appt_eligible(c, now_naive, policy)]
        walkins = [c for c in candidates if c.entry_class == 'walkin']

        chosen = _select(db, service_point_id, session_date, elig_appts, walkins, now_naive, policy)
        if chosen is not None:
            # re-fetch + lock + re-check 'checked_in' (กันชนกับ transition อื่นระหว่าง read→write)
            locked = (db.query(models.QueueEntry)
                      .filter(models.QueueEntry.id == chosen.id)
                      .with_for_update()
                      .one_or_none())
            if locked is not None and locked.status == 'checked_in':
                qs._apply_transition(db, locked, 'called', actor)
                entry = locked

    db.commit()   # commit เสมอ -> ปล่อย advisory lock
    if entry is not None:
        db.refresh(entry)
    return entry
