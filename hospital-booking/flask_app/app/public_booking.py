# flask_app/app/public_booking.py - Public Booking Routes

import os
import requests
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, g
import secrets
import time
from datetime import datetime, timedelta, date
import calendar
import json
from redis import Redis
from rq import Queue
from typing import Optional, Dict, Set

from .utils.url_helper import build_url_with_context
from .core.tenant_manager import TenantManager
from .services.otp_service import otp_service
from .services.email_service import queue_otp_email
from .services.sms_service import queue_otp_sms


# สร้าง Blueprint
public_bp = Blueprint('booking', __name__, url_prefix='/book')

def get_fastapi_url():
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

def get_subdomain():
    """Get subdomain from TenantManager"""
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    return subdomain


def fetch_unavailable_override_dates(subdomain: str, template_id: Optional[int]) -> Dict[str, str]:
    if not subdomain:
        return {}

    try:
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/date-overrides"
        )
    except Exception:
        return {}

    if not response.ok:
        return {}

    overrides = response.json().get('date_overrides', [])
    blocked: Dict[str, str] = {}

    for override in overrides:
        override_template_id = override.get('template_id')
        scope = override.get('template_scope')
        if not override.get('is_unavailable'):
            continue

        is_global = scope == 'global'
        is_matching_template = template_id is not None and override_template_id == template_id

        if not (is_global or is_matching_template):
            continue

        override_date = override.get('date')
        if not override_date:
            continue

        label = override.get('reason') or 'วันหยุดพิเศษ'
        blocked[override_date] = label

    return blocked


def fetch_holiday_dates(subdomain: str, years: Set[int]) -> Dict[str, str]:
    if not subdomain or not years:
        return {}

    holidays_map: Dict[str, str] = {}
    base_url = f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/holidays"

    for target_year in sorted(years):
        try:
            response = requests.get(base_url, params={'year': target_year, 'is_active': True})
        except Exception:
            continue

        if not response.ok:
            continue

        try:
            holidays = response.json()
        except ValueError:
            holidays = []

        for holiday in holidays or []:
            holiday_date = holiday.get('date') if isinstance(holiday, dict) else None
            if not holiday_date:
                continue
            holidays_map[holiday_date] = holiday.get('name', 'วันหยุด') if isinstance(holiday, dict) else 'วันหยุด'

    return holidays_map

# --- Public Booking Pages (No Login Required) ---

@public_bp.route('/')
def booking_home():
    """หน้าแรก - เลือกประเภทการนัด"""
    subdomain = get_subdomain()
    
    if not subdomain:
        # ลองดูจาก session
        subdomain = session.get('last_subdomain')
        
        if not subdomain:
            # แสดงหน้าให้เลือกโรงพยาบาล หรือ error
            flash('กรุณาเลือกโรงพยาบาล', 'info')
            
            # Option 1: กลับไปหน้าหลัก
            return redirect(url_for('main.index'))
            
            # Option 2: แสดงหน้าเลือกโรงพยาบาล (ถ้ามี)
            # return render_template('booking/select_hospital.html')
    
    # บันทึก subdomain ล่าสุดใน session
    session['last_subdomain'] = subdomain
    
    # Get event types from API
    try:
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types"
        )
        if response.ok:
            data = response.json()
            event_types = data.get('event_types', [])
            
            # Filter active only
            active_types = [et for et in event_types if et.get('is_active', True)]
            
            return render_template('booking/home.html',
                                 event_types=active_types,
                                 subdomain=subdomain)
        else:
            flash('ไม่สามารถโหลดประเภทการนัดได้', 'error')
            return render_template('booking/error.html', subdomain=subdomain)
            
    except Exception as e:
        print(f"Error loading event types: {e}")
        flash('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error')
        return render_template('booking/error.html', subdomain=subdomain)

@public_bp.route('/service/<int:event_type_id>')
def book_service(event_type_id):
    """หน้าจองนัด - เลือกวันเวลา"""
    subdomain = get_subdomain()
    
    try:
        # 1. Get event type details พร้อม availability
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types"
        )
        if not response.ok:
            flash('ไม่สามารถโหลดข้อมูลได้', 'error')
            return redirect(build_url_with_context('booking.booking_home'))
            
        data = response.json()
        event_types = data.get('event_types', [])
        event_type = next((et for et in event_types if et['id'] == event_type_id), None)
        
        if not event_type:
            flash('ไม่พบประเภทการนัดที่เลือก', 'error')
            return redirect(build_url_with_context('booking.booking_home'))
        
        # 2. Get availability schedule from template
        availability_schedule = {}
        if event_type.get('template_id'):
            avail_response = requests.get(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{event_type['template_id']}/details"
            )
            if avail_response.ok:
                avail_data = avail_response.json()
                availability_schedule = avail_data.get('schedule', {})
        
        template_id = event_type.get('template_id')
        now = datetime.now()
        today_date = now.date()
        unavailable_overrides = fetch_unavailable_override_dates(subdomain, template_id)

        max_advance_days = event_type.get('max_advance_days')
        max_date = None
        holiday_years: Set[int] = {today_date.year}
        if isinstance(max_advance_days, int):
            max_date = today_date + timedelta(days=max_advance_days)
            holiday_years.add(max_date.year)
        else:
            holiday_years.add(today_date.year + 1)

        holiday_dates = fetch_holiday_dates(subdomain, holiday_years)

        calendar_data = generate_calendar_for_booking(
            now.year,
            now.month,
            availability_schedule,
            unavailable_dates=unavailable_overrides,
            holiday_dates=holiday_dates,
            max_advance_days=max_advance_days,
            today=today_date
        )
        
        return render_template('booking/select_time.html',
                             event_type=event_type,
                             calendar_data=calendar_data,
                             availability_schedule=availability_schedule,
                             subdomain=subdomain,
                             today=today_date.isoformat(),
                             current_month=now.month,
                             current_year=now.year,
                             max_advance_days=max_advance_days)
                             
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('booking.booking_home'))

@public_bp.route('/api/availability/<int:event_type_id>/<date>')
def get_availability(event_type_id, date):
    """AJAX endpoint - ดึง available slots"""
    subdomain = get_subdomain()
    
    try:
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/availability/{event_type_id}",
            params={'date': date}
        )
        
        if response.ok:
            return jsonify(response.json())
        else:
            return jsonify({'error': 'Failed to get availability'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@public_bp.route('/confirm', methods=['POST'])
def confirm_booking():
    """หน้ายืนยันข้อมูลการจอง"""
    subdomain = get_subdomain()
    
    # รับข้อมูลจาก form
    event_type_id = request.form.get('event_type_id')
    event_type_name = request.form.get('event_type_name')
    date = request.form.get('date')
    time = request.form.get('time')
    
    if not all([event_type_id, date, time]):
        flash('กรุณาเลือกวันและเวลา', 'error')
        return redirect(request.referrer)
    
    # Format date for display
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    date_display = date_obj.strftime('%d/%m/%Y')

    provider_choices = []
    provider_selection_required = False
    provider_error_message = None
    provider_auto_label = 'ไม่ต้องการเลือก (ให้ระบบเลือกให้)'

    fastapi_base = get_fastapi_url()
    availability_url = f"{fastapi_base}/api/v1/tenants/{subdomain}/booking/availability/{event_type_id}"

    try:
        availability_response = requests.get(availability_url, params={'date': date}, timeout=10)
        if availability_response.ok:
            availability_data = availability_response.json()
            template_id = availability_data.get('template_id')
            provider_selection_required = bool(availability_data.get('requires_provider_assignment'))

            if provider_selection_required:
                slots = availability_data.get('slots', [])
                slot_info = next((slot for slot in slots if slot.get('time') == time), None)

                if not slot_info or not slot_info.get('available'):
                    flash('ช่วงเวลาที่เลือกไม่พร้อมใช้งานแล้ว กรุณาเลือกใหม่อีกครั้ง', 'error')
                    return redirect(build_url_with_context('booking.book_service', event_type_id=event_type_id))

                available_provider_ids = slot_info.get('available_provider_ids') or []

                if template_id and available_provider_ids:
                    providers_url = f"{fastapi_base}/api/v1/tenants/{subdomain}/availability/templates/{template_id}/providers"
                    providers_response = requests.get(providers_url, timeout=10)

                    if providers_response.ok:
                        providers_data = providers_response.json().get('providers', [])
                        for assignment in providers_data:
                            provider_id = assignment.get('provider_id')
                            if provider_id not in available_provider_ids:
                                continue
                            if assignment.get('is_active') is False:
                                continue

                            provider_choices.append({
                                'id': provider_id,
                                'name': assignment.get('name'),
                                'title': assignment.get('title'),
                                'is_primary': assignment.get('is_primary'),
                                'priority': assignment.get('priority'),
                                'can_auto_assign': assignment.get('can_auto_assign')
                            })

                        provider_choices.sort(key=lambda item: (
                            0 if item.get('is_primary') else 1,
                            item.get('priority') if item.get('priority') is not None else 999,
                            (item.get('name') or '').lower()
                        ))
                    else:
                        provider_error_message = 'ไม่สามารถโหลดรายชื่อผู้ให้บริการได้'
                else:
                    provider_error_message = 'ไม่มีผู้ให้บริการว่างในช่วงเวลาที่เลือก'
        else:
            provider_error_message = 'ไม่สามารถตรวจสอบความพร้อมของช่วงเวลาที่เลือกได้'
    except requests.exceptions.RequestException:
        provider_error_message = 'ไม่สามารถเชื่อมต่อเพื่อตรวจสอบรายชื่อผู้ให้บริการได้'
    except Exception:
        provider_error_message = 'เกิดข้อผิดพลาดในการเตรียมข้อมูลผู้ให้บริการ'

    # สร้าง token สำหรับหน้านี้
    from .utils.security import generate_booking_token
    booking_token = generate_booking_token()
    
    # เก็บ token ใน session เพื่อตรวจสอบภายหลัง
    if 'booking_tokens' not in session:
        session['booking_tokens'] = []
    session['booking_tokens'].append(booking_token)
    
    # ลบ token เก่าที่หมดอายุ (เก็บแค่ 10 อันล่าสุด)
    session['booking_tokens'] = session['booking_tokens'][-10:]
    
    return render_template('booking/confirm.html',
                         booking_token=booking_token,
                         event_type_id=event_type_id,
                         event_type_name=event_type_name,
                         date=date,
                         date_display=date_display,
                         time=time,
                         provider_choices=provider_choices,
                         provider_selection_required=provider_selection_required,
                         provider_auto_label=provider_auto_label,
                         provider_error_message=provider_error_message,
                         subdomain=subdomain)

@public_bp.route('/create', methods=['POST'])
def create_booking():
    """สร้างการจองจริง"""
    subdomain = get_subdomain()

    # 1. ตรวจสอบ Honeypot
    honeypot_fields = ['website', 'url']
    for field in honeypot_fields:
        if request.form.get(field):
            # Bot detected - แสดงหน้าสำเร็จปลอมๆ
            print(f"🤖 Bot detected: filled honeypot field '{field}'")
            fake_ref = f"BK-{datetime.now().strftime('%H%M%S')}"
            return redirect(build_url_with_context('booking.success', reference=fake_ref))
            
        
    # 2. ตรวจสอบ Time-based Token
    from .utils.security import verify_booking_token
    
    token = request.form.get('booking_token')
    if not token:
        flash('ข้อมูลการจองไม่ถูกต้อง', 'error')
        return redirect(build_url_with_context('booking.booking_home'))
    
    valid, message = verify_booking_token(token)
    if not valid:
        flash(message, 'error')
        return redirect(build_url_with_context('booking.booking_home'))
    
    # ตรวจสอบว่า token นี้เคยใช้แล้วหรือไม่
    if 'used_tokens' not in session:
        session['used_tokens'] = []
    
    if token in session['used_tokens']:
        flash('ข้อมูลการจองนี้ถูกใช้แล้ว', 'error')
        return redirect(build_url_with_context('booking.booking_home'))
    
    # 3. ตรวจสอบ Session Rate Limit
    if 'booking_history' not in session:
        session['booking_history'] = []
    
    # ลบประวัติเก่า (เกิน 1 ชั่วโมง)
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    session['booking_history'] = [
        b for b in session['booking_history'] 
        if b['time'] > cutoff
    ]
    
    # ตรวจสอบจำนวนการจอง
    if len(session['booking_history']) >= 5:
        remaining_time = 60 - int((datetime.now() - datetime.fromisoformat(session['booking_history'][0]['time'])).seconds / 60)
        flash(f'คุณจองบ่อยเกินไป กรุณารออีก {remaining_time} นาที', 'error')
        return redirect(build_url_with_context('booking.booking_home'))
    
    # รับข้อมูลจาก form
    guest_email = request.form.get('guest_email', '').strip()
    guest_phone = request.form.get('guest_phone', '').strip()
    
    booking_data = {
        'event_type_id': int(request.form.get('event_type_id')),
        'date': request.form.get('date'),
        'time': request.form.get('time'),
        'guest_name': request.form.get('guest_name'),
        'guest_email': guest_email if guest_email else None,  # ส่ง None แทน ''
        'guest_phone': guest_phone if guest_phone else None,  # ส่ง None แทน ''
        'notes': request.form.get('notes', '')
    }

    provider_id_raw = request.form.get('provider_id', '').strip()
    if provider_id_raw:
        try:
            booking_data['provider_id'] = int(provider_id_raw)
        except ValueError:
            pass
    
    # Validate
    if not booking_data['guest_name']:
        flash('กรุณากรอกชื่อ', 'error')
        return redirect(request.referrer)
    
    if not booking_data['guest_email'] and not booking_data['guest_phone']:
        flash('กรุณากรอก email หรือเบอร์โทรอย่างน้อย 1 อย่าง', 'error')
        return redirect(request.referrer)
    
    # เก็บประวัติการจอง
    session['booking_history'].append({
        'time': datetime.now().isoformat(),
        'email': request.form.get('guest_email'),
        'phone': request.form.get('guest_phone')
    })
    
    # เก็บ token ที่ใช้แล้ว
    session['used_tokens'].append(token)
    session['used_tokens'] = session['used_tokens'][-20:]  # เก็บแค่ 20 อันล่าสุด
    
    # Send to API
    try:
        response = requests.post(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/create",
            json=booking_data
        )
        
        if response.ok:
            result = response.json()
            return redirect(build_url_with_context('booking.success', reference=result['booking_reference']))
            
        
        else:
            error_data = response.json()
            print(f"API Error: {error_data}")  # เพิ่ม logging
            flash(error_data.get('detail', 'ไม่สามารถจองได้'), 'error')
            return redirect(request.referrer)
            
    except Exception as e:
        print(f"Booking error: {e}")
        import traceback
        traceback.print_exc()  # เพิ่มเพื่อดู full error
        flash('เกิดข้อผิดพลาดในการจอง', 'error')
        return redirect(request.referrer)

@public_bp.route('/success/<reference>')
def success(reference):
    """หน้าแสดงผลการจองสำเร็จ"""
    subdomain = get_subdomain()
    
    # Get booking details
    try:
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/{reference}"
        )
        
        if response.ok:
            booking = response.json()
            
            # Format datetime
            dt = datetime.fromisoformat(booking['appointment_datetime'])
            thai_day_names = ['วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์', 'วันอาทิตย์']
            thai_month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']

            booking['time_display'] = dt.strftime('%H:%M')
            # สร้าง key ใหม่ชื่อ full_date_display เพื่อเก็บรูปแบบวันที่ที่ต้องการ
            booking['full_date_display'] = f"{thai_day_names[dt.weekday()]}ที่ {dt.day} {thai_month_names[dt.month - 1]} {dt.year + 543}"
                        
            return render_template('booking/success.html',
                                 booking=booking,
                                 subdomain=subdomain)
        else:
            flash('ไม่พบข้อมูลการจอง', 'error')
            return redirect(build_url_with_context('booking.booking_home'))
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('booking.booking_home'))

@public_bp.route('/manage/<reference>')
def manage_booking(reference):
    """หน้าจัดการการจอง (ดู/เลื่อน/ยกเลิก)"""
    subdomain = get_subdomain()

    reference = reference.upper().strip()
    
    try:
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/{reference}"
        )
        
        if response.ok:
            booking = response.json()
            
            # Format datetime
            dt = datetime.fromisoformat(booking['appointment_datetime'])
            end_dt = datetime.fromisoformat(booking['end_time']) if booking.get('end_time') else None
            
            thai_day_names = ['วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์', 'วันอาทิตย์']
            thai_month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']

            booking['time_display'] = dt.strftime('%H:%M')
            booking['end_time_display'] = end_dt.strftime('%H:%M') if end_dt else None
            booking['full_date_display'] = f"{thai_day_names[dt.weekday()]}ที่ {dt.day} {thai_month_names[dt.month - 1]} {dt.year + 543}"
            booking['date_display'] = dt.strftime('%d/%m/%Y')
            
            # Add formatted time range
            if booking['end_time_display']:
                booking['time_range_display'] = f"{booking['time_display']} - {booking['end_time_display']}"
            else:
                booking['time_range_display'] = booking['time_display']
            
            return render_template('booking/manage.html',
                                 booking=booking,
                                 subdomain=subdomain)
        else:
            # ไม่พบข้อมูล - แสดง error พร้อมกลับไปหน้าค้นหา
            flash(f'ไม่พบข้อมูลการจองหมายเลข {reference}', 'error')
            # เก็บ reference ที่ค้นหาไว้ใน session เพื่อใส่ใน form อัตโนมัติ
            session['last_search_value'] = reference
            return redirect(build_url_with_context('booking.my_appointments'))
            
    except Exception as e:
        flash('เกิดข้อผิดพลาดในการค้นหา', 'error')
        return redirect(build_url_with_context('booking.my_appointments'))

@public_bp.route('/reschedule/<reference>', methods=['GET', 'POST'])
def reschedule_booking(reference):
    """เลื่อนนัด - ปรับปรุงให้ดึงข้อมูล availability จาก API"""
    subdomain = get_subdomain()
    
    if request.method == 'POST':
        # Process reschedule
        reschedule_data = {
            'booking_reference': reference,
            'new_date': request.form.get('new_date'),
            'new_time': request.form.get('new_time'),
            'reason': request.form.get('reason', '')
        }
        
        try:
            response = requests.post(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/reschedule",
                json=reschedule_data
            )
            
            if response.ok:
                result = response.json()
                flash(result.get('message', 'เลื่อนนัดเรียบร้อยแล้ว'), 'success')
                return redirect(build_url_with_context('booking.success',
                                      reference=result.get('booking_reference', reference)))
            else:
                error = response.json()
                flash(error.get('detail', 'ไม่สามารถเลื่อนนัดได้'), 'error')
                
        except Exception as e:
            flash('เกิดข้อผิดพลาด', 'error')
    
    # GET - Show reschedule form
    try:
        # 1. ดึงข้อมูลการจอง
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/{reference}"
        )
        
        if not response.ok:
            flash('ไม่พบข้อมูลการจอง', 'error')
            return redirect(build_url_with_context('booking.booking_home'))
            
        booking = response.json()

        # จัดรูปแบบวันที่และเวลาให้อ่านง่าย
        dt = datetime.fromisoformat(booking['appointment_datetime'])
        thai_day_names = ['วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์', 'วันอาทิตย์']
        thai_month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
        
        # สร้าง Key ใหม่สำหรับแสดงผลโดยเฉพาะ
        booking['time_display'] = dt.strftime('%H:%M')
        booking['full_date_display'] = f"{thai_day_names[dt.weekday()]}ที่ {dt.day} {thai_month_names[dt.month - 1]} {dt.year + 543}"
        # ------------------------
        
        if not booking.get('can_reschedule'):
            flash('ไม่สามารถเลื่อนนัดได้ (ใกล้เวลานัดเกินไป)', 'error')
            return redirect(build_url_with_context('booking.manage_booking', reference=reference))
        
        # 2. ดึงข้อมูล event type และ availability
        event_type_id = booking.get('event_type', {}).get('id')
        event_type_data = None
        availability_schedule = {}
        template_id = None
        
        if event_type_id:
            try:
                # ดึง event type details พร้อม availability schedule
                evt_response = requests.get(
                    f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types/{event_type_id}",
                    timeout=10
                )
                if evt_response.ok:
                    event_type_data = evt_response.json()
                    booking['event_type_full'] = event_type_data
                    template_id = event_type_data.get('template_id')
                    
                    # ดึง availability schedule จาก template
                    if template_id:
                        avail_response = requests.get(
                            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{template_id}/details",
                            timeout=10
                        )
                        if avail_response.ok:
                            availability_data = avail_response.json()
                            availability_schedule = availability_data.get('schedule', {})
                            booking['availability_schedule'] = availability_schedule
                        else:
                            print(f"⚠️ Warning: Failed to fetch availability template {template_id}")
                    else:
                        print(f"⚠️ Warning: Event type {event_type_id} has no template_id")
                else:
                    print(f"⚠️ Warning: Failed to fetch event type {event_type_id}: {evt_response.status_code}")
            except Exception as e:
                print(f"❌ Error fetching event type data: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ No event_type_id found in booking data")
        
        # ตรวจสอบว่ามีข้อมูลครบหรือไม่
        if not availability_schedule:
            flash('ไม่สามารถโหลดข้อมูลตารางเวลาได้ กรุณาติดต่อผู้ดูแลระบบ', 'error')
            return redirect(build_url_with_context('booking.manage_booking', reference=reference))
        
        now = datetime.now()
        today_date = now.date()
        unavailable_overrides = fetch_unavailable_override_dates(subdomain, template_id)

        max_advance_days = event_type_data.get('max_advance_days') if event_type_data else None
        holiday_years: Set[int] = {today_date.year}
        if isinstance(max_advance_days, int):
            max_date = today_date + timedelta(days=max_advance_days)
            holiday_years.add(max_date.year)
        else:
            holiday_years.add(today_date.year + 1)

        holiday_dates = fetch_holiday_dates(subdomain, holiday_years)

        calendar_data = generate_calendar_for_booking(
            now.year,
            now.month,
            availability_schedule,
            unavailable_dates=unavailable_overrides,
            holiday_dates=holiday_dates,
            max_advance_days=max_advance_days,
            today=today_date
        )
        
        return render_template('booking/reschedule.html',
                             booking=booking,
                             calendar_data=calendar_data,
                             availability_schedule=availability_schedule, 
                             subdomain=subdomain,
                             today=today_date.isoformat(),
                             max_advance_days=max_advance_days)
                             
    except Exception as e:
        print(f"Error in reschedule: {e}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('booking.booking_home'))

@public_bp.route('/cancel/<reference>', methods=['POST'])
def cancel_booking(reference):
    """ยกเลิกนัด"""
    subdomain = get_subdomain()
    
    cancel_data = {
        'booking_reference': reference,
        'reason': request.form.get('reason', '')
    }
    
    try:
        response = requests.post(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/cancel",
            json=cancel_data
        )
        
        if response.ok:
            flash('ยกเลิกนัดเรียบร้อยแล้ว', 'success')
            return render_template('booking/cancelled.html',
                                 reference=reference,
                                 subdomain=subdomain)
        else:
            error = response.json()
            flash(error.get('detail', 'ไม่สามารถยกเลิกได้'), 'error')
            return redirect(build_url_with_context('booking.manage_booking', reference=reference))
            
    except Exception as e:
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('booking.manage_booking', reference=reference))
    
# ค้นหานัดหมายของฉัน

@public_bp.route('/my-appointments')
def my_appointments():
    """หน้าค้นหานัดหมายของฉัน"""
    subdomain = get_subdomain()
    
    if not subdomain:
        flash('กรุณาเลือกโรงพยาบาล', 'info')
        return redirect(url_for('main.index'))
    
    return render_template('booking/my_appointments.html',
                         subdomain=subdomain)

@public_bp.route('/search-appointments', methods=['POST'])
def search_appointments():
    subdomain = get_subdomain()
    
    search_type = request.form.get('search_type')
    search_value = request.form.get('search_value')
    
    if not search_value:
        flash('กรุณากรอกข้อมูลที่ต้องการค้นหา', 'error')
        return redirect(request.referrer)
    
    # ถ้าเป็น reference ไปหน้า manage โดยตรง ไม่ต้อง OTP
    if search_type == 'reference':
        search_value = search_value.upper().strip()
        # ใช้ build_url_with_context แทน url_for
        return redirect(build_url_with_context('booking.manage_booking', 
                                              reference=search_value))
    
    # Email และ Phone ต้องใช้ OTP
    otp = otp_service.generate_otp(search_value, expiration=300)
    
    if search_type == 'email':
        queue_otp_email(search_value, otp)
        flash(f'รหัส OTP ถูกส่งไปยัง {search_value}', 'info')
        
    elif search_type == 'phone':
        clean_phone = search_value.replace(' ', '').replace('-', '')
        queue_otp_sms(clean_phone, otp)
        masked_phone = search_value[:3] + '****' + search_value[-3:]
        flash(f'รหัส OTP ถูกส่งไปยัง {masked_phone}', 'info')
    
    # Store search info in session (สำหรับ email/phone เท่านั้น)
    session['pending_search'] = {
        'type': search_type,
        'value': search_value
    }
    
    return render_template('booking/verify_otp.html',
                         search_type=search_type,
                         search_value=search_value,
                         subdomain=subdomain)

@public_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    subdomain = get_subdomain()
    otp_input = request.form.get('otp')
    
    if 'pending_search' not in session:
        flash('ข้อมูลหมดอายุ กรุณาค้นหาใหม่', 'error')
        return redirect(url_for('booking.my_appointments'))
    
    search_info = session['pending_search']
    
    # Verify OTP using pyotp
    success, message = otp_service.verify_otp(search_info['value'], otp_input)
    
    if not success:
        flash(message, 'error')
        # Check remaining time
        time_remaining = otp_service.get_time_remaining(search_info['value'])
        return render_template('booking/verify_otp.html',
                             search_type=search_info['type'],
                             search_value=search_info['value'],
                             time_remaining=time_remaining,
                             subdomain=subdomain)
    
    # Clear session
    session.pop('pending_search', None)
    
    # Fetch appointments
    try:
        response = requests.post(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/search",
            json={
                'search_type': search_info['type'],
                'search_value': search_info['value']
            }
        )
        
        if response.ok:
            appointments = response.json()
            # Process appointments...
            return render_template('booking/appointment_list.html',
                                 appointments=appointments,
                                 subdomain=subdomain)
    except:
        flash('เกิดข้อผิดพลาด', 'error')
    
    return redirect(build_url_with_context('booking.my_appointments'))

@public_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP"""
    if 'pending_search' not in session:
        return jsonify({'error': 'Session expired'}), 400
    
    search_info = session['pending_search']
    
    # Check if can resend (wait 60 seconds between resends)
    last_resend = session.get('last_otp_resend', 0)
    if time.time() - last_resend < 60:
        wait_time = 60 - int(time.time() - last_resend)
        return jsonify({'error': f'กรุณารอ {wait_time} วินาที'}), 429
    
    # Generate new OTP
    otp = otp_service.generate_otp(search_info['value'], expiration=300)
    
    # Send OTP
    if search_info['type'] == 'email':
        queue_otp_email(search_info['value'], otp)
    elif search_info['type'] == 'phone':
        queue_otp_sms(search_info['value'], otp)
    
    session['last_otp_resend'] = time.time()
    
    return jsonify({'success': True, 'message': 'ส่ง OTP ใหม่แล้ว'})

# --- Helper Functions ---
def generate_calendar_for_booking(
    year: int,
    month: int,
    availability_schedule: Dict[str, list],
    unavailable_dates: Optional[Dict[str, str]] = None,
    holiday_dates: Optional[Dict[str, str]] = None,
    max_advance_days: Optional[int] = None,
    today: Optional[date] = None
) -> Dict[str, object]:
    import calendar

    today = today or date.today()
    unavailable_dates = unavailable_dates or {}
    holiday_dates = holiday_dates or {}

    first_weekday, days_in_month = calendar.monthrange(year, month)
    first_weekday = (first_weekday + 1) % 7

    month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']

    max_date = None
    if isinstance(max_advance_days, int):
        max_date = today + timedelta(days=max_advance_days)

    weeks = []
    current_week = []
    
    print(f"\nฟའ️ Generating calendar for {month_names[month-1]} {year+543}")
    print(f"   Today: {today}")
    print(f"   Max advance: {max_advance_days} days (until {max_date})")
    print(f"   Availability schedule: {list(availability_schedule.keys())}")

    for _ in range(first_weekday):
        current_week.append({
            'day': 0,
            'date': None,
            'available': False,
            'past': False,
            'today': False,
            'disabled_reason': None,
            'disabled_label': '',
            'is_holiday': False,
            'is_special_closure': False,
            'beyond_max_range': False
        })

    available_count = 0
    for day in range(1, days_in_month + 1):
        date_obj = date(year, month, day)
        python_weekday = date_obj.weekday()
        our_weekday = 0 if python_weekday == 6 else python_weekday + 1
        iso_date = date_obj.isoformat()

        is_past = date_obj < today
        is_today = date_obj == today
        is_override_closed = iso_date in unavailable_dates
        is_holiday = iso_date in holiday_dates
        beyond_max_range = max_date is not None and date_obj > max_date

        disabled_reason = None
        disabled_label = ''

        if is_past:
            disabled_reason = 'past'
            disabled_label = 'วันที่ผ่านมาแล้ว'
        elif beyond_max_range:
            disabled_reason = 'beyond_max_range'
            if isinstance(max_advance_days, int):
                disabled_label = f'จองได้ไม่เกิน {max_advance_days} วันล่วงหน้า'
        elif is_override_closed:
            disabled_reason = 'override'
            disabled_label = unavailable_dates.get(iso_date, 'วันหยุดพิเศษ')
        elif is_holiday:
            disabled_reason = 'holiday'
            disabled_label = holiday_dates.get(iso_date, 'วันหยุด')

        has_schedule = str(our_weekday) in availability_schedule
        is_available = has_schedule and disabled_reason is None and not is_past
        
        # Debug logging สำหรับวันที่ควรจะว่าง
        if day <= 10:  # แสดงแค่ 10 วันแรก
            day_name = ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'][our_weekday]
            status = "✅" if is_available else "❌"
            reason = ""
            if not has_schedule:
                reason = f"(no schedule for day {our_weekday})"
            elif is_past:
                reason = "(past)"
            elif beyond_max_range:
                reason = "(beyond max)"
            elif is_override_closed:
                reason = "(override)"
            elif is_holiday:
                reason = f"(holiday: {disabled_label})"
            
            print(f"   {status} {date_obj} ({day_name}): weekday={our_weekday}, has_schedule={has_schedule} {reason}")
        
        if is_available:
            available_count += 1

        current_week.append({
            'day': day,
            'date': iso_date,
            'day_of_week': our_weekday,
            'available': is_available,
            'past': is_past,
            'today': is_today,
            'disabled_reason': disabled_reason,
            'disabled_label': disabled_label,
            'is_holiday': is_holiday,
            'is_special_closure': is_override_closed,
            'beyond_max_range': beyond_max_range
        })

        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []

    if current_week:
        while len(current_week) < 7:
            current_week.append({
                'day': 0,
                'date': None,
                'available': False,
                'past': False,
                'today': False,
                'disabled_reason': None,
                'disabled_label': '',
                'is_holiday': False,
                'is_special_closure': False,
                'beyond_max_range': False
            })
        weeks.append(current_week)
    
    print(f"   ฟມ̌ RESULT: {available_count} available days found\n")

    return {
        'year': year,
        'month': month,
        'month_name': month_names[month - 1],
        'weeks': weeks,
        'prev_month': month - 1 if month > 1 else 12,
        'prev_year': year if month > 1 else year - 1,
        'next_month': month + 1 if month < 12 else 1,
        'next_year': year if month < 12 else year + 1,
        'can_go_previous': date(year, month, 1) > today.replace(day=1)
    }

@public_bp.route('/api/calendar/<year>/<month>')
def get_calendar(year, month):
    """เพิ่ม AJAX endpoint สำหรับดึง calendar data และเพิ่ม debug logging"""
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return jsonify({'error': 'Invalid year or month format'}), 400
    
    subdomain = get_subdomain()
    event_type_id = request.args.get('event_type_id', type=int)
    
    availability_schedule = {}
    unavailable_overrides: Dict[str, str] = {}
    holiday_dates: Dict[str, str] = {}
    max_advance_days: Optional[int] = None
    template_id: Optional[int] = None
    today_date = date.today()
    holiday_years: Set[int] = {year, today_date.year}
    
    print(f"\nฟ้འ️ [Calendar AJAX] event_type_id={event_type_id}, year={year}, month={month}")
    
    if event_type_id:
        try:
            # ดึง event type และ availability
            evt_url = f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types/{event_type_id}"
            print(f"  ฟມ̩ Fetching event type: {evt_url}")
            
            response = requests.get(evt_url, timeout=10)
            if response.ok:
                event_type = response.json()
                max_advance_days = event_type.get('max_advance_days')
                template_id = event_type.get('template_id')
                
                print(f"  ✅ Event type loaded: template_id={template_id}, max_advance_days={max_advance_days}")
                
                if template_id:
                    avail_url = f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{template_id}/details"
                    print(f"  ฟມ̩ Fetching availability: {avail_url}")
                    
                    avail_response = requests.get(avail_url, timeout=10)
                    if avail_response.ok:
                        avail_data = avail_response.json()
                        availability_schedule = avail_data.get('schedule', {})
                        print(f"  ✅ Availability loaded: {len(availability_schedule)} days configured")
                        print(f"     Days: {list(availability_schedule.keys())}")
                    else:
                        print(f"  ❌ Failed to fetch availability: {avail_response.status_code}")
                else:
                    print(f"  ⚠️ No template_id in event type!")

                unavailable_overrides = fetch_unavailable_override_dates(subdomain, template_id)
                print(f"  ฟྩ️ Date overrides: {len(unavailable_overrides)} dates blocked")

                if isinstance(max_advance_days, int):
                    max_date = today_date + timedelta(days=max_advance_days)
                    holiday_years.add(max_date.year)
                else:
                    holiday_years.add(today_date.year + 1)

                holiday_dates = fetch_holiday_dates(subdomain, holiday_years)
                print(f"  ฟྩ‍♂️ Holidays: {len(holiday_dates)} days")
            else:
                print(f"  ❌ Failed to fetch event type: {response.status_code}")
        except Exception as e:
            print(f"  ❌ Error in calendar AJAX: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nฟྣ Generating calendar with availability_schedule: {availability_schedule}\n")
    
    calendar_data = generate_calendar_for_booking(
        year,
        month,
        availability_schedule,
        unavailable_dates=unavailable_overrides,
        holiday_dates=holiday_dates,
        max_advance_days=max_advance_days,
        today=today_date
    )
    return jsonify(calendar_data)

def generate_calendar_with_availability(year, month, availability_schedule):
    """Generate calendar data with correct day alignment"""
    import calendar
    from datetime import datetime, date
    
    # Set first day of week to Sunday (6)
    calendar.setfirstweekday(calendar.SUNDAY)
    
    # Get calendar
    cal = calendar.monthcalendar(year, month)
    today = date.today()
    
    month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    
    weeks_data = []
    for week in cal:
        week_info = []
        for day in week:
            if day == 0:
                week_info.append({
                    'day': 0,
                    'available': False
                })
            else:
                date_obj = date(year, month, day)
                # Python weekday: 0=Monday, 6=Sunday
                # We need: 0=Sunday, 6=Saturday for our system
                python_weekday = date_obj.weekday()
                our_weekday = 0 if python_weekday == 6 else python_weekday + 1
                
                # Check if this day is available
                is_available = str(our_weekday) in availability_schedule and date_obj >= today
                
                week_info.append({
                    'day': day,
                    'date': date_obj.isoformat(),
                    'day_of_week': our_weekday,
                    'available': is_available,
                    'past': date_obj < today,
                    'today': date_obj == today
                })
        weeks_data.append(week_info)
    
    return {
        'year': year,
        'month': month,
        'month_name': month_names[month - 1],
        'weeks': weeks_data
    }

def generate_calendar_data(year, month):
    """Generate calendar data for display"""
    cal = calendar.monthcalendar(year, month)
    
    # Get month name in Thai
    month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    
    return {
        'year': year,
        'month': month,
        'month_name': month_names[month - 1],
        'weeks': cal,
        'prev_month': month - 1 if month > 1 else 12,
        'prev_year': year if month > 1 else year - 1,
        'next_month': month + 1 if month < 12 else 1,
        'next_year': year if month < 12 else year + 1
    }