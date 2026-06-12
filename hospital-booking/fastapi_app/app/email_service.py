# fastapi_app/app/email_service.py
"""
ส่งอีเมลแจ้งเตือนการนัดหมายจริงผ่าน SMTP (อ่านค่า MAIL_* จาก .env)

ออกแบบให้เรียกจาก FastAPI BackgroundTasks ด้วยค่า primitive (str/datetime) เท่านั้น
ห้ามส่ง ORM object เข้ามา เพราะ background task ทำงานหลัง DB session ถูกปิดแล้ว
การส่งล้มเหลวจะ log ไว้เฉยๆ ไม่ throw — อีเมลต้องไม่ทำให้การจองล้มเหลว
"""

import os
import logging
import smtplib
from datetime import datetime
from email.charset import BASE64, Charset
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


def _utf8_base64_charset():
    """utf-8 charset ที่บังคับ body เป็น BASE64 เสมอ

    ห้ามใช้ _charset='utf-8' (string) — flask_mail แก้ charset registry ระดับ global
    (body_encoding → None = 8bit) เมื่อ process ไหน import flask_mail (เช่น RQ worker
    ที่ import app.*) ข้อความไทยจะกลายเป็น raw 8-bit แล้ว smtplib.sendmail
    ที่ encode เป็น ascii จะล้มเหลว
    """
    cs = Charset('utf-8')
    cs.body_encoding = BASE64
    return cs

logger = logging.getLogger("nuddee.email")

THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


def format_thai_datetime(dt: datetime) -> str:
    """เช่น 'วันพุธที่ 17 มิถุนายน 2569 เวลา 09:30 น.'"""
    day_name = THAI_DAYS[dt.weekday()]
    month = THAI_MONTHS[dt.month - 1]
    return f"วัน{day_name}ที่ {dt.day} {month} {dt.year + 543} เวลา {dt.strftime('%H:%M')} น."


def _smtp_config():
    return {
        'server': os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
        'port': int(os.environ.get('MAIL_PORT', '587')),
        'use_tls': os.environ.get('MAIL_USE_TLS', 'true').strip().lower() in ('true', '1', 'yes'),
        'username': os.environ.get('MAIL_USERNAME'),
        'password': os.environ.get('MAIL_PASSWORD'),
        'sender': (
            os.environ.get('MAIL_DEFAULT_SENDER')
            or os.environ.get('EMAIL_SENDER')
            or os.environ.get('MAIL_USERNAME')
        ),
    }


def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """ส่งอีเมลหนึ่งฉบับ คืน True/False — ไม่ throw"""
    cfg = _smtp_config()
    if not (cfg['username'] and cfg['password']):
        logger.warning("MAIL_USERNAME/MAIL_PASSWORD ไม่ได้ตั้งค่า — ข้ามการส่งอีเมลถึง %s (%s)", to, subject)
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = formataddr(("NudDee นัดดี", cfg['sender']))
    msg['To'] = to
    msg.attach(MIMEText(text_body, 'plain', _charset=_utf8_base64_charset()))
    msg.attach(MIMEText(html_body, 'html', _charset=_utf8_base64_charset()))

    try:
        if cfg['port'] == 465:
            server = smtplib.SMTP_SSL(cfg['server'], cfg['port'], timeout=20)
        else:
            server = smtplib.SMTP(cfg['server'], cfg['port'], timeout=20)
        with server:
            if cfg['use_tls'] and cfg['port'] != 465:
                server.starttls()
            server.login(cfg['username'], cfg['password'])
            server.sendmail(cfg['sender'], [to], msg.as_string())
        print(f"📧 ส่งอีเมล '{subject}' ถึง {to} สำเร็จ", flush=True)
        logger.info("ส่งอีเมล '%s' ถึง %s สำเร็จ", subject, to)
        return True
    except Exception as e:
        print(f"❌ ส่งอีเมล '{subject}' ถึง {to} ล้มเหลว: {e}", flush=True)
        logger.exception("ส่งอีเมล '%s' ถึง %s ล้มเหลว", subject, to)
        return False


def _appointment_email(
    kind: str,
    to: str,
    hospital_name: str,
    booking_reference: str,
    event_name: str = None,
    start_time: datetime = None,
    guest_name: str = None,
):
    """สร้างและส่งอีเมลนัดหมายตามชนิด: confirmed / rescheduled / cancelled"""
    kinds = {
        'confirmed': {
            'subject': f"ยืนยันการนัดหมาย {booking_reference} - {hospital_name}",
            'title': "การนัดหมายของคุณได้รับการยืนยันแล้ว",
            'intro': "ขอบคุณที่ใช้บริการ รายละเอียดการนัดหมายของคุณมีดังนี้",
            'color': "#16a34a",
        },
        'rescheduled': {
            'subject': f"แจ้งเปลี่ยนแปลงนัดหมาย {booking_reference} - {hospital_name}",
            'title': "นัดหมายของคุณถูกเปลี่ยนแปลง",
            'intro': "นัดหมายของคุณได้รับการอัปเดต รายละเอียดล่าสุดมีดังนี้",
            'color': "#d97706",
        },
        'cancelled': {
            'subject': f"ยกเลิกนัดหมาย {booking_reference} - {hospital_name}",
            'title': "นัดหมายของคุณถูกยกเลิกแล้ว",
            'intro': "นัดหมายต่อไปนี้ถูกยกเลิกเรียบร้อยแล้ว หากต้องการนัดใหม่สามารถจองได้อีกครั้ง",
            'color': "#dc2626",
        },
    }
    meta = kinds[kind]

    greeting = f"เรียน คุณ{guest_name}" if guest_name else "เรียน ผู้รับบริการ"
    when = format_thai_datetime(start_time) if start_time else None

    rows = [("รหัสนัดหมาย", booking_reference)]
    if event_name:
        rows.append(("บริการ", event_name))
    if when:
        rows.append(("วันและเวลา", when))
    rows.append(("สถานที่", hospital_name))

    detail_html = "".join(
        f"<tr>"
        f"<td style='padding:8px 16px 8px 0;color:#6b7280;white-space:nowrap;vertical-align:top;'>{label}</td>"
        f"<td style='padding:8px 0;color:#111827;font-weight:600;'>{value}</td>"
        f"</tr>"
        for label, value in rows
    )

    html_body = f"""\
<div style="font-family:'Helvetica Neue',Arial,'Noto Sans Thai',sans-serif;background:#f3f4f6;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
    <div style="background:{meta['color']};padding:20px 28px;">
      <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">{meta['title']}</p>
    </div>
    <div style="padding:28px;">
      <p style="margin:0 0 8px;color:#111827;">{greeting}</p>
      <p style="margin:0 0 20px;color:#4b5563;">{meta['intro']}</p>
      <table style="border-collapse:collapse;width:100%;font-size:15px;">{detail_html}</table>
      <p style="margin:24px 0 0;color:#6b7280;font-size:13px;">
        หากต้องการเลื่อนหรือยกเลิกนัด กรุณาใช้รหัสนัดหมายข้างต้นที่หน้าค้นหานัดหมาย
        หรือติดต่อ {hospital_name} โดยตรง
      </p>
    </div>
    <div style="padding:16px 28px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;color:#9ca3af;font-size:12px;">อีเมลฉบับนี้ส่งโดยระบบนัดหมายออนไลน์ NudDee (นัดดี) — กรุณาอย่าตอบกลับ</p>
    </div>
  </div>
</div>
"""

    text_lines = [greeting, "", meta['title'], meta['intro'], ""]
    text_lines += [f"{label}: {value}" for label, value in rows]
    text_lines += ["", f"หากต้องการเลื่อนหรือยกเลิกนัด กรุณาติดต่อ {hospital_name} พร้อมแจ้งรหัสนัดหมาย"]
    text_body = "\n".join(text_lines)

    send_email(to, meta['subject'], html_body, text_body)


def send_appointment_confirmation(to, hospital_name, booking_reference, event_name, start_time, guest_name=None):
    _appointment_email('confirmed', to, hospital_name, booking_reference, event_name, start_time, guest_name)


def send_appointment_reschedule(to, hospital_name, booking_reference, event_name, start_time, guest_name=None):
    _appointment_email('rescheduled', to, hospital_name, booking_reference, event_name, start_time, guest_name)


def send_appointment_cancellation(to, hospital_name, booking_reference, event_name=None, start_time=None, guest_name=None):
    _appointment_email('cancelled', to, hospital_name, booking_reference, event_name, start_time, guest_name)


def send_appointment_reschedule_request(to, hospital_name, booking_reference,
                                        event_name=None, start_time=None, guest_name=None,
                                        reschedule_link=None, reason=None):
    """สถานพยาบาลขอความร่วมมือให้ผู้รับบริการเลื่อนนัดเอง พร้อมลิงก์เลือกเวลาใหม่"""
    greeting = f"เรียน คุณ{guest_name}" if guest_name else "เรียน ผู้รับบริการ"
    subject = f"ขอความร่วมมือเลื่อนนัดหมาย {booking_reference} - {hospital_name}"
    when = format_thai_datetime(start_time) if start_time else None

    rows = [("รหัสนัดหมาย", booking_reference)]
    if event_name:
        rows.append(("บริการ", event_name))
    if when:
        rows.append(("นัดเดิม", when))
    rows.append(("สถานที่", hospital_name))
    if reason:
        rows.append(("เหตุผล", reason))

    detail_html = "".join(
        f"<tr>"
        f"<td style='padding:8px 16px 8px 0;color:#6b7280;white-space:nowrap;vertical-align:top;'>{label}</td>"
        f"<td style='padding:8px 0;color:#111827;font-weight:600;'>{value}</td>"
        f"</tr>"
        for label, value in rows
    )

    link_html = ""
    if reschedule_link:
        link_html = (
            f"<div style='margin-top:24px;text-align:center;'>"
            f"<a href='{reschedule_link}' style='display:inline-block;background:#9333ea;color:#ffffff;"
            f"padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;'>เลือกเวลานัดใหม่</a>"
            f"</div>"
            f"<p style='margin:16px 0 0;color:#9ca3af;font-size:12px;text-align:center;'>"
            f"หรือเปิดลิงก์: {reschedule_link}</p>"
        )

    html_body = f"""\
<div style="font-family:'Helvetica Neue',Arial,'Noto Sans Thai',sans-serif;background:#f3f4f6;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
    <div style="background:#d97706;padding:20px 28px;">
      <p style="margin:0;color:#ffffff;font-size:18px;font-weight:700;">ขอความร่วมมือเลื่อนนัดหมาย</p>
    </div>
    <div style="padding:28px;">
      <p style="margin:0 0 8px;color:#111827;">{greeting}</p>
      <p style="margin:0 0 20px;color:#4b5563;">
        {hospital_name} ขออภัยในความไม่สะดวก และขอความร่วมมือเลื่อนนัดหมายของคุณ
        กรุณาเลือกวันและเวลาใหม่ที่สะดวกผ่านลิงก์ด้านล่าง
      </p>
      <table style="border-collapse:collapse;width:100%;font-size:15px;">{detail_html}</table>
      {link_html}
    </div>
    <div style="padding:16px 28px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;color:#9ca3af;font-size:12px;">อีเมลฉบับนี้ส่งโดยระบบนัดหมายออนไลน์ NudDee (นัดดี) — กรุณาอย่าตอบกลับ</p>
    </div>
  </div>
</div>
"""

    text_lines = [greeting, "",
                  f"{hospital_name} ขอความร่วมมือเลื่อนนัดหมายของคุณ", ""]
    text_lines += [f"{label}: {value}" for label, value in rows]
    if reschedule_link:
        text_lines += ["", f"เลือกเวลานัดใหม่ได้ที่: {reschedule_link}"]
    text_body = "\n".join(text_lines)

    send_email(to, subject, html_body, text_body)
