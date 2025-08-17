# flask_app/app/public_booking.py - Public Booking Routes

import os
import requests
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, g
from datetime import datetime, timedelta
import calendar
import json
from .utils.url_helper import build_url_with_context

# สร้าง Blueprint
public_bp = Blueprint('booking', __name__, url_prefix='/book')

def get_fastapi_url():
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

def get_subdomain():
    """Get subdomain from request - ปรับปรุงให้ดีขึ้น"""
    # 1. ตรวจสอบจาก g object ก่อน (จาก middleware)
    if hasattr(g, 'subdomain') and g.subdomain:
        return g.subdomain
    
    # 2. ตรวจสอบจาก query parameter
    subdomain = request.args.get('subdomain')
    if subdomain:
        return subdomain
    
    # 3. ตรวจสอบจาก hostname
    hostname = request.host.split(':')[0]
    parts = hostname.split('.')
    
    # ตรวจสอบ subdomain pattern
    if len(parts) > 1:
        potential_subdomain = parts[0]
        # Check for *.localhost pattern
        if len(parts) == 2 and parts[1] == 'localhost':
            return potential_subdomain
        # Check for normal subdomain (not www, api, localhost, etc.)
        elif potential_subdomain not in ['localhost', 'www', 'api', '127', '192']:
            return potential_subdomain
    
    # 4. ถ้าไม่พบ subdomain ให้ return None แทน default
    return None

# --- Public Booking Pages (No Login Required) ---

@public_bp.route('/')
def booking_home():
    """หน้าแรก - เลือกประเภทการนัด"""
    subdomain = get_subdomain()
    
    if not subdomain:
        flash('กรุณาระบุโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))  # กลับไปหน้าหลัก
    
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
            return render_template('booking/error.html')
            
    except Exception as e:
        print(f"Error loading event types: {e}")
        flash('เกิดข้อผิดพลาดในการเชื่อมต่อ', 'error')
        return render_template('booking/error.html')

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
        
        # 3. Generate calendar data
        today = datetime.now()
        calendar_data = generate_calendar_for_booking(
            today.year, 
            today.month, 
            availability_schedule
        )
        
        return render_template('booking/select_time.html',
                             event_type=event_type,
                             calendar_data=calendar_data,
                             availability_schedule=availability_schedule,
                             subdomain=subdomain,
                             today=today.date().isoformat(),
                             current_month=today.month,
                             current_year=today.year)
                             
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
    if len(session['booking_history']) >= 3:
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
            booking['full_date_display'] = f"{thai_day_names[dt.weekday()]}ที่ {dt.day} {thai_month_names[dt.month - 1]} {dt.year + 543}"

            
            return render_template('booking/manage.html',
                                 booking=booking,
                                 subdomain=subdomain)
        else:
            flash('ไม่พบข้อมูลการจอง', 'error')
            return redirect(build_url_with_context('booking.booking_home'))
            
    except Exception as e:
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('booking.booking_home'))

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
                flash('เลื่อนนัดเรียบร้อยแล้ว', 'success')
                return redirect(build_url_with_context('booking.success',
                                      reference=result['new_booking_reference']))
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
        if event_type_id:
            # ดึง event type details พร้อม availability schedule
            evt_response = requests.get(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types/{event_type_id}"
            )
            if evt_response.ok:
                event_type_data = evt_response.json()
                booking['event_type_full'] = event_type_data
                
                # ดึง availability schedule จาก template
                if event_type_data.get('template_id'):
                    avail_response = requests.get(
                        f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{event_type_data['template_id']}/details"
                    )
                    if avail_response.ok:
                        availability_data = avail_response.json()
                        booking['availability_schedule'] = availability_data.get('schedule', {})
        
        # 3. สร้าง calendar data
        today = datetime.now()
        calendar_data = generate_calendar_for_booking(
            today.year, 
            today.month,
            booking.get('availability_schedule', {})
        )
        
        return render_template('booking/reschedule.html',
                             booking=booking,
                             calendar_data=calendar_data,
                             availability_schedule=booking.get('availability_schedule', {}), 
                             subdomain=subdomain,
                             today=today.isoformat())
                             
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

# --- Helper Functions ---
def generate_calendar_for_booking(year, month, availability_schedule):
    """Generate calendar data with correct day alignment"""
    import calendar
    from datetime import date
    
    # Get first day of month (0=Monday, 6=Sunday)
    first_weekday, days_in_month = calendar.monthrange(year, month)
    # Convert to Sunday start (0=Sunday, 6=Saturday)
    first_weekday = (first_weekday + 1) % 7
    
    today = date.today()
    
    month_names = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                   'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    
    # Build calendar weeks
    weeks = []
    current_week = []
    
    # Add empty days at start
    for _ in range(first_weekday):
        current_week.append({
            'day': 0,
            'date': None,
            'available': False,
            'past': False
        })
    
    # Add days of month
    for day in range(1, days_in_month + 1):
        date_obj = date(year, month, day)
        # Python weekday: 0=Monday, 6=Sunday
        python_weekday = date_obj.weekday()
        # Convert to our system: 0=Sunday, 1=Monday, etc.
        our_weekday = 0 if python_weekday == 6 else python_weekday + 1
        
        # Check if available
        is_available = str(our_weekday) in availability_schedule and date_obj >= today
        
        current_week.append({
            'day': day,
            'date': date_obj.isoformat(),
            'day_of_week': our_weekday,
            'available': is_available,
            'past': date_obj < today,
            'today': date_obj == today
        })
        
        # Start new week if needed
        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []
    
    # Add remaining days
    if current_week:
        while len(current_week) < 7:
            current_week.append({
                'day': 0,
                'date': None,
                'available': False,
                'past': False
            })
        weeks.append(current_week)
    
    return {
        'year': year,
        'month': month,
        'month_name': month_names[month - 1],
        'weeks': weeks,
        'prev_month': month - 1 if month > 1 else 12,
        'prev_year': year if month > 1 else year - 1,
        'next_month': month + 1 if month < 12 else 1,
        'next_year': year if month < 12 else year + 1,
        'can_go_previous': date(year, month, 1) > date.today().replace(day=1)
    }

# เพิ่ม AJAX endpoint สำหรับ calendar navigation
@public_bp.route('/api/calendar/<int:year>/<int:month>')
def get_calendar(year, month):
    """AJAX endpoint สำหรับดึง calendar data"""
    subdomain = get_subdomain()
    event_type_id = request.args.get('event_type_id', type=int)
    
    availability_schedule = {}
    
    if event_type_id:
        try:
            # ดึง event type และ availability
            response = requests.get(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types/{event_type_id}"
            )
            if response.ok:
                event_type = response.json()
                if event_type.get('template_id'):
                    avail_response = requests.get(
                        f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{event_type['template_id']}/details"
                    )
                    if avail_response.ok:
                        availability_schedule = avail_response.json().get('schedule', {})
        except:
            pass
    
    calendar_data = generate_calendar_for_booking(year, month, availability_schedule)
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