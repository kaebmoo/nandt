"""Grace rule engine (§5.3) — จัดคลาส entry ตอน check-in: มาตรงเวลา→priority, มาสาย→demote

กฎ (แผน §2 ข้อ 6 + §5.3):
- อยู่ช่วงผ่อนผัน [slot_start - grace_before_min, slot_end + grace_after_min] → 'appointment' (priority เต็ม)
- มาสายเกินช่วง (วันเดียวกัน/ข้าม session) → ตาม late_arrival_policy:
    demote_to_walkin (default) → 'walkin'
    reslot_to_current          → 'appointment' (ย้าย session เป็นปัจจุบัน — ทำที่ caller; ตอนนี้คง priority)
    require_rebook             → NoShowError (ไม่รับเข้าคิว ต้องจองใหม่)
- **มาก่อนเวลา (early, ก่อน grace_before)** → ไม่ลงโทษ คง 'appointment' — ความตรงเวลาไม่ใช่ความผิดที่มาเช้า
  (การที่ยังเรียกไม่ได้เพราะ slot ยังไม่ถึง เป็นเรื่องของ priority_service eligibility ไม่ใช่ grace)

slot window: window booking → เวลาของ session ที่ผูก; exact → appointment.start_time/end_time (ดู A1 §12)
เวลาในระบบจองเป็น naive local (Asia/Bangkok); ฟังก์ชันนี้ normalize now ให้ naive ก่อนเทียบ
"""

import datetime

from shared_db import models


class NoShowError(ValueError):
    """late_arrival_policy='require_rebook' + มาสายเกินช่วงผ่อนผัน → ต้องจองใหม่ (ไม่รับเข้าคิว)"""


def get_grace_policy(db, service_point_id):
    """grace_policy ของ service_point (ถ้ามี) ไม่งั้น default ของ tenant (service_point_id IS NULL)"""
    pol = (db.query(models.GracePolicy)
           .filter(models.GracePolicy.service_point_id == service_point_id)
           .first())
    if pol is None:
        pol = (db.query(models.GracePolicy)
               .filter(models.GracePolicy.service_point_id.is_(None))
               .first())
    return pol


def _naive(dt):
    """ตัด tzinfo ออกถ้ามี — เทียบกับเวลานัดที่เก็บเป็น naive local (Bangkok)"""
    if dt is not None and getattr(dt, 'tzinfo', None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _slot_window(appointment, session):
    """คืน (slot_start, slot_end) เป็น datetime naive — หรือ (None, None) ถ้าระบุไม่ได้

    - window booking (มี session): ใช้เวลาของ session บนวันของนัด
    - exact: ใช้ appointment.start_time / end_time ตรง ๆ
    """
    if session is not None and appointment.start_time is not None:
        on_date = _naive(appointment.start_time).date()
        return (datetime.datetime.combine(on_date, session.start_time),
                datetime.datetime.combine(on_date, session.end_time))
    return _naive(appointment.start_time), _naive(appointment.end_time)


def classify_on_checkin(appointment, now, policy, session=None) -> str:
    """คืน entry_class ('appointment' | 'walkin') ตามกฎ grace; อาจ raise NoShowError

    ไม่ commit / ไม่แตะ DB (pure) — caller (check_in) เป็นคนเขียน reclass event + สร้าง entry
    """
    slot_start, slot_end = _slot_window(appointment, session)
    if slot_start is None or slot_end is None:
        return 'appointment'   # ไม่มีข้อมูลเวลา → ให้ประโยชน์ก่อน (priority เต็ม)

    now_n = _naive(now)
    window_start = slot_start - datetime.timedelta(minutes=policy.grace_before_min)
    window_end = slot_end + datetime.timedelta(minutes=policy.grace_after_min)

    if now_n < window_start:
        return 'appointment'   # มาก่อนช่วงผ่อนผัน — ไม่ลงโทษ (รอ eligibility)
    if now_n <= window_end:
        return 'appointment'   # อยู่ในช่วงผ่อนผัน — priority เต็ม

    # มาสายเกินช่วงผ่อนผัน → ตาม late_arrival_policy
    lap = policy.late_arrival_policy
    if lap == 'require_rebook':
        raise NoShowError(
            f"appointment {getattr(appointment, 'id', '?')} มาสายเกินช่วงผ่อนผัน "
            f"(นโยบาย require_rebook) — ต้องจองใหม่")
    if lap == 'reslot_to_current':
        return 'appointment'   # คง priority; การย้าย session เป็นปัจจุบันทำที่ caller (ดู TODO check_in)
    return 'walkin'            # demote_to_walkin (default)
