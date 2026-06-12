# flask_app/app/services/appointment_notifications.py
"""
แจ้งผู้รับบริการเมื่อเจ้าหน้าที่เปลี่ยนแปลงนัดหมายจาก dashboard

ลำดับช่องทางการแจ้ง:
1. มีอีเมล → ส่งอีเมลผ่าน RQ queue (template เดียวกับฝั่ง public booking)
2. ไม่มีอีเมลแต่มีเบอร์โทร:
   - ถ้า ENABLE_SMS_NOTIFICATIONS=true และตั้งค่า NT_SMS_* ครบ → ส่ง SMS
   - ค่าเริ่มต้น (ปิด SMS) → คืนข้อความเตือนให้เจ้าหน้าที่ "โทรแจ้ง" พร้อมเบอร์
3. ไม่มีทั้งสองอย่าง → เตือนว่าไม่มีช่องทางติดต่อ

ทุกฟังก์ชัน notify_* คืน (message, flash_category) สำหรับแจ้งผลแก่เจ้าหน้าที่เสมอ
และความล้มเหลวของการแจ้งต้องไม่ทำให้ action หลัก (เลื่อน/ยกเลิกนัด) ล้มเหลว
"""

import os
import logging

from .redis_connection import redis_manager
from .sms_service import send_notification_sms

logger = logging.getLogger(__name__)


def _sms_enabled():
    """SMS เป็น option — เปิดด้วย ENABLE_SMS_NOTIFICATIONS=true และต้องตั้งค่า NT_SMS_* ครบ"""
    flag = os.environ.get('ENABLE_SMS_NOTIFICATIONS', 'false').strip().lower() in ('true', '1', 'yes')
    configured = all(os.environ.get(k) for k in
                     ('NT_SMS_USER', 'NT_SMS_PASS', 'NT_SMS_SENDER', 'NT_SMS_HOST', 'NT_SMS_API'))
    return flag and configured


def format_thai_phone(phone):
    """0812345678 → 081-234-5678, 021234567 → 02-123-4567"""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if len(digits) == 10 and digits.startswith('0'):
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if len(digits) == 9 and digits.startswith('0'):
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"
    return phone


def _thai_short_datetime(dt):
    if not dt:
        return '-'
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year + 543} เวลา {dt.strftime('%H:%M')} น."


# --- RQ jobs (worker import ผ่าน path: app.services.appointment_notifications.*) ---

def send_appointment_email_job(kind, to, hospital_name, booking_reference,
                               event_name=None, start_time=None, guest_name=None):
    """ส่งอีเมลแจ้งเลื่อน/ยกเลิกนัด — ใช้ template กลางของระบบ (fastapi_app.app.email_service)"""
    from fastapi_app.app.email_service import (
        send_appointment_cancellation,
        send_appointment_reschedule,
    )
    sender = {
        'cancelled': send_appointment_cancellation,
        'rescheduled': send_appointment_reschedule,
    }[kind]
    sender(to, hospital_name, booking_reference, event_name, start_time, guest_name)


def send_reschedule_request_email_job(to, hospital_name, booking_reference,
                                      event_name=None, start_time=None, guest_name=None,
                                      reschedule_link=None, reason=None):
    from fastapi_app.app.email_service import send_appointment_reschedule_request
    send_appointment_reschedule_request(
        to, hospital_name, booking_reference,
        event_name=event_name, start_time=start_time, guest_name=guest_name,
        reschedule_link=reschedule_link, reason=reason,
    )


def _enqueue_or_run(job_func, **kwargs):
    """enqueue เข้า RQ; ถ้า Redis ล่มให้ส่งตรงเป็น fallback — คืน True/False"""
    try:
        queue = redis_manager.get_queue('default')
        job = queue.enqueue(job_func, job_timeout='5m', **kwargs)
        logger.info(f"Queued {job_func.__name__} job {job.id} for {kwargs.get('to')}")
        return True
    except Exception:
        logger.exception(f"enqueue {job_func.__name__} ล้มเหลว — ลองส่งตรง")
        try:
            job_func(**kwargs)
            return True
        except Exception:
            logger.exception(f"{job_func.__name__} ส่งตรงก็ล้มเหลว")
            return False


def _queue_sms(phone, message):
    try:
        queue = redis_manager.get_queue('default')
        queue.enqueue(send_notification_sms, phone_number=phone, message=message)
        return True
    except Exception:
        logger.exception("enqueue SMS ล้มเหลว")
        return False


# --- public API ---

def notify_patient_appointment_change(kind, *, hospital_name, booking_reference,
                                      event_name=None, start_time=None, guest_name=None,
                                      guest_email=None, guest_phone=None,
                                      email_already_sent=False):
    """แจ้งผู้รับบริการว่านัดถูกเลื่อน ('rescheduled') หรือยกเลิก ('cancelled')

    email_already_sent=True ใช้กรณี action วิ่งผ่าน FastAPI ซึ่งส่งอีเมลให้แล้ว
    (เช่น admin reschedule) เพื่อไม่ส่งซ้ำ
    """
    action_text = 'การยกเลิกนัด' if kind == 'cancelled' else 'การเลื่อนนัด'
    name_part = f"คุณ{guest_name} " if guest_name else "ผู้รับบริการ "

    if guest_email:
        if not email_already_sent:
            ok = _enqueue_or_run(
                send_appointment_email_job,
                kind=kind, to=guest_email, hospital_name=hospital_name,
                booking_reference=booking_reference, event_name=event_name,
                start_time=start_time, guest_name=guest_name,
            )
            if not ok:
                return (f"ส่งอีเมลแจ้ง{action_text}ไม่สำเร็จ — กรุณาติดต่อ{name_part}"
                        f"ที่ {guest_email}" + (f" หรือโทร {format_thai_phone(guest_phone)}" if guest_phone else ""),
                        'warning')
        return (f"ระบบส่งอีเมลแจ้ง{action_text}ถึง {guest_email} แล้ว", 'info')

    if guest_phone:
        pretty_phone = format_thai_phone(guest_phone)
        if _sms_enabled():
            if kind == 'cancelled':
                sms = f"[{hospital_name}] นัดหมาย {booking_reference} ของท่านถูกยกเลิกแล้ว"
            else:
                sms = (f"[{hospital_name}] นัดหมาย {booking_reference} ของท่านถูกเลื่อนเป็น "
                       f"{_thai_short_datetime(start_time)}")
            if _queue_sms(guest_phone, sms):
                return (f"ระบบส่ง SMS แจ้ง{action_text}ไปที่ {pretty_phone} แล้ว", 'info')
        return (f"นัดนี้ไม่มีอีเมล — กรุณาโทรแจ้ง{action_text}แก่{name_part}"
                f"ที่เบอร์ {pretty_phone}", 'warning')

    return (f"นัดนี้ไม่มีอีเมลและเบอร์โทร — หากมีช่องทางอื่นกรุณาแจ้ง{action_text}"
            f"แก่ผู้รับบริการโดยตรง", 'warning')


def notify_reschedule_request(*, hospital_name, booking_reference, event_name=None,
                              start_time=None, guest_name=None, guest_email=None,
                              guest_phone=None, reschedule_link=None, reason=None):
    """ส่งคำขอให้ผู้รับบริการเลื่อนนัดเอง (พร้อมลิงก์เลือกเวลาใหม่)"""
    name_part = f"คุณ{guest_name} " if guest_name else "ผู้รับบริการ "

    if guest_email:
        ok = _enqueue_or_run(
            send_reschedule_request_email_job,
            to=guest_email, hospital_name=hospital_name,
            booking_reference=booking_reference, event_name=event_name,
            start_time=start_time, guest_name=guest_name,
            reschedule_link=reschedule_link, reason=reason,
        )
        if ok:
            return (f"ระบบส่งอีเมลขอเลื่อนนัดพร้อมลิงก์เลือกเวลาใหม่ถึง {guest_email} แล้ว", 'info')
        return (f"ส่งอีเมลไม่สำเร็จ — กรุณาติดต่อ{name_part}โดยตรง", 'warning')

    if guest_phone:
        pretty_phone = format_thai_phone(guest_phone)
        if _sms_enabled() and reschedule_link:
            sms = (f"[{hospital_name}] ขอความร่วมมือเลื่อนนัด {booking_reference} "
                   f"เลือกเวลาใหม่ที่ {reschedule_link}")
            if _queue_sms(guest_phone, sms):
                return (f"ระบบส่ง SMS ขอเลื่อนนัดไปที่ {pretty_phone} แล้ว", 'info')
        return (f"นัดนี้ไม่มีอีเมล — กรุณาโทรแจ้งขอเลื่อนนัดกับ{name_part}"
                f"ที่เบอร์ {pretty_phone}", 'warning')

    return ("นัดนี้ไม่มีอีเมลและเบอร์โทร — หากมีช่องทางอื่นกรุณาแจ้งผู้รับบริการโดยตรง", 'warning')
