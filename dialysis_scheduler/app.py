# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
import os
import csv
import io
from datetime import datetime, timedelta
import json
import requests
from dotenv import load_dotenv, set_key

from teamup_api import TeamupAPI
from config import Config, TEAMUP_API_KEY, CALENDAR_ID
from forms import AppointmentForm
import uuid

app = Flask(__name__)
app.config.from_object(Config)
Config.init_app()

# สร้าง TeamupAPI instance (จะถูกกำหนดค่าเมื่อผู้ใช้ login)
teamup_api = None

# ลองใช้ค่าจาก .env file (ถ้ามี)
if TEAMUP_API_KEY and CALENDAR_ID:
    try:
        print(f"กำลังเชื่อมต่อกับ TeamUp API โดยใช้ค่าจาก .env file...")
        teamup_api = TeamupAPI(TEAMUP_API_KEY, CALENDAR_ID)
        success, message = teamup_api.check_access()
        if success:
            print(f"เชื่อมต่อกับ TeamUp API สำเร็จ!")
        else:
            print(f"ไม่สามารถเชื่อมต่อกับ TeamUp API: {message}")
            teamup_api = None
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการเชื่อมต่อกับ TeamUp API: {e}")
        teamup_api = None

@app.route('/')
def index():
    """หน้าแรกของแอปพลิเคชัน"""
    global teamup_api
    api_connected = is_api_connected()
    
    summary_data = None
    if api_connected:
        try:
            # ดึงข้อมูลปฏิทินย่อย
            subcals = teamup_api.get_subcalendars()
            subcalendar_count = len(subcals.get('subcalendars', []))
            
            # ดึงข้อมูลการนัดหมายวันนี้
            today = datetime.now()
            start_date = datetime(today.year, today.month, today.day)
            end_date = start_date + timedelta(days=1)
            
            events = teamup_api.get_events(start_date=start_date, end_date=end_date)
            today_appointments = len(events.get('events', []))
            
            # สร้าง summary_data
            summary_data = {
                'subcalendar_count': subcalendar_count,
                'today_appointments': today_appointments,
                'subcalendars': subcals.get('subcalendars', [])[:5]
            }
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสรุป: {e}")
    
    return render_template('index.html', api_connected=api_connected, summary_data=summary_data)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """หน้าตั้งค่าการเชื่อมต่อ API"""
    global teamup_api
    
    # ตรวจสอบการเชื่อมต่อที่มีอยู่
    current_connection = {
        'api_key': TEAMUP_API_KEY or '',
        'calendar_id': CALENDAR_ID or '',
        'is_connected': teamup_api is not None
    }
    
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        calendar_id = request.form.get('calendar_id')
        save_to_env = request.form.get('save_to_env') == 'true'
        
        if not api_key or not calendar_id:
            flash('กรุณากรอก API Key และ Calendar ID', 'danger')
            return render_template('setup.html', current=current_connection)
        
        # ทำความสะอาด Calendar ID
        if calendar_id.startswith('https://teamup.com/'):
            calendar_id = calendar_id.replace('https://teamup.com/', '')
        
        # สร้าง TeamupAPI instance
        test_api = TeamupAPI(api_key, calendar_id)
        
        # ทดสอบการเชื่อมต่อ
        try:
            success, message = test_api.check_access()
            
            if success:
                # บันทึกลงไฟล์ .env ถ้าเลือกตัวเลือกนี้
                if save_to_env:
                    try:
                        env_path = '.env'
                        
                        # สร้างไฟล์ .env ใหม่หากยังไม่มี
                        if not os.path.exists(env_path):
                            with open(env_path, 'w') as f:
                                f.write("# Dialysis Scheduler Configuration\n")
                        
                        # บันทึกค่าลงไฟล์ .env
                        set_key(env_path, 'TEAMUP_API', api_key)
                        set_key(env_path, 'CALENDAR_ID', calendar_id)
                        
                        # โหลดค่าใหม่
                        load_dotenv(override=True)
                        
                        flash('บันทึกการตั้งค่าลงในไฟล์ .env สำเร็จ!', 'success')
                    except Exception as e:
                        flash(f'ไม่สามารถบันทึกการตั้งค่าลงในไฟล์ .env: {e}', 'warning')
                
                # อัปเดต TeamupAPI instance
                teamup_api = test_api
                
                # บันทึกข้อมูลลงใน session
                session['api_key'] = api_key
                session['calendar_id'] = calendar_id
                
                flash('เชื่อมต่อ API สำเร็จ!', 'success')
                return redirect(url_for('index'))
            else:
                flash(f'เชื่อมต่อ API ไม่สำเร็จ: {message}', 'danger')
                return render_template('setup.html', current=current_connection)
                
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
            return render_template('setup.html', current=current_connection)
    
    return render_template('setup.html', current=current_connection)

@app.route('/subcalendars')
def subcalendars():
    """หน้าแสดงรายการปฏิทินย่อย"""
    global teamup_api
    
    # สร้าง instance ใหม่ถ้ายังไม่มี
    if teamup_api is None and 'api_key' in session and 'calendar_id' in session:
        teamup_api = TeamupAPI(session['api_key'], session['calendar_id'])
    
    # ถ้ายังไม่มี teamup_api ให้แสดงข้อความเตือน
    if teamup_api is None:
        flash('กรุณาเชื่อมต่อ API ก่อนเข้าถึงปฏิทินย่อย', 'warning')
        return redirect(url_for('setup'))
    
    try:
        # ดึงข้อมูลปฏิทินย่อย
        subcals = teamup_api.get_subcalendars()
        return render_template('subcalendars.html', subcalendars=subcals.get('subcalendars', []))
        
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลปฏิทินย่อย: {e}', 'danger')
        return render_template('subcalendars.html', subcalendars=[])

@app.route('/appointments')
def appointments():
    """หน้าแสดงรายการนัดหมาย"""
    if not is_api_connected():
        flash('กรุณาเชื่อมต่อ API ก่อน', 'warning')
        return redirect(url_for('setup'))
    
    # สร้าง form
    form = AppointmentForm()
    
    # ดึงรายการปฏิทินย่อยสำหรับ dropdown
    subcals = teamup_api.get_subcalendars()
    form.calendar_name.choices = [('', 'เลือกปฏิทินย่อย')] + [
        (subcal['name'], subcal['name']) for subcal in subcals.get('subcalendars', [])
    ]
    
    # สร้าง unique form token
    form.form_token.data = str(uuid.uuid4())
    
    # สร้างวันที่สำหรับค่าเริ่มต้น
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')
    next_month = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # รับพารามิเตอร์ subcalendar_id จาก URL
    selected_subcalendar_id = request.args.get('subcalendar_id', '')
    
    return render_template('appointments.html', 
                          form=form,
                          subcalendars=subcals.get('subcalendars', []),
                          today=today,
                          end_date=next_month,
                          selected_subcalendar_id=selected_subcalendar_id)

@app.route('/get_events')
def get_events():
    """API endpoint สำหรับดึงรายการกิจกรรม"""
    if not is_api_connected():
        return jsonify({'error': 'ไม่ได้เชื่อมต่อ API'}), 401
    
    try:
        # รับพารามิเตอร์จาก URL
        start_date = request.args.get('start_date', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'))
        subcalendar_id = request.args.get('subcalendar_id', '')
        event_id = request.args.get('event_id', '')
        
        # ถ้ามี event_id ให้ดึงรายละเอียดเฉพาะกิจกรรมนั้น
        if event_id:
            try:
                response = requests.get(
                    f"{teamup_api.base_url}/events/{event_id}",
                    headers=teamup_api.headers
                )
                if response.status_code == 200:
                    event_data = response.json()
                    event = event_data['event']
                    
                    # เพิ่มข้อมูลชื่อปฏิทินย่อย
                    if 'subcalendar_id' in event:
                        try:
                            # ดึงข้อมูลปฏิทินย่อย
                            subcals = teamup_api.get_subcalendars()
                            for subcal in subcals.get('subcalendars', []):
                                if subcal['id'] == event['subcalendar_id']:
                                    event['subcalendar_display'] = subcal['name']
                                    break
                            else:
                                # ถ้าไม่เจอชื่อปฏิทินย่อย
                                event['subcalendar_display'] = f'ปฏิทิน #{event["subcalendar_id"]}'
                        except Exception as e:
                            print(f"Error getting subcalendar name: {e}")
                            event['subcalendar_display'] = f'ปฏิทิน #{event.get("subcalendar_id", "")}'
                    else:
                        event['subcalendar_display'] = 'ไม่ระบุปฏิทิน'
                    
                    return jsonify({'events': [event]})
                else:
                    return jsonify({'error': f'ไม่สามารถดึงข้อมูลนัดหมาย: {response.text}', 'events': []}), 404
            except Exception as e:
                return jsonify({'error': str(e), 'events': []}), 500
        
        # ถ้าไม่มี event_id ให้ดึงรายการกิจกรรมตามปกติ
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # แปลง subcalendar_id เป็น integer ถ้ามีค่า
        subcalendar_filter = None
        if subcalendar_id:
            try:
                subcalendar_filter = int(subcalendar_id)
            except ValueError:
                pass
        
        events = teamup_api.get_events(
            start_date=start_dt,
            end_date=end_dt,
            subcalendar_id=subcalendar_filter
        )
        
        return jsonify(events)
        
    except Exception as e:
        return jsonify({'error': str(e), 'events': []}), 500

# แก้ไข route /create_appointment ใน app.py
@app.route('/create_appointment', methods=['POST'])
def create_appointment():
    """API endpoint สำหรับสร้างนัดหมายใหม่ - Hybrid Approach"""
    if not is_api_connected():
        return jsonify({'error': 'ไม่ได้เชื่อมต่อ API'}), 401
    
    form = AppointmentForm()
    
    # ดึงรายการปฏิทินย่อยสำหรับ validation
    subcals = teamup_api.get_subcalendars()
    form.calendar_name.choices = [
        (subcal['name'], subcal['name']) for subcal in subcals.get('subcalendars', [])
    ]
    
    if form.validate_on_submit():
        # ป้องกันการส่งซ้ำด้วย session
        form_token = form.form_token.data
        if form_token and form_token in session.get('processed_forms', []):
            # สร้าง form token ใหม่แล้วส่งกลับ
            new_token = str(uuid.uuid4())
            return jsonify({
                'error': 'คำขอนี้ถูกประมวลผลแล้ว กรุณาลองอีกครั้ง',
                'new_form_token': new_token
            }), 400
        
        try:
            # ตรวจสอบ recurring validation
            if form.is_recurring.data:
                is_valid, error_msg = form.validate_recurring_days()
                if not is_valid:
                    # สร้าง form token ใหม่เมื่อ validation ล้มเหลว
                    new_token = str(uuid.uuid4())
                    return jsonify({
                        'error': error_msg,
                        'new_form_token': new_token
                    }), 400
            
            # บันทึก token เพื่อป้องกันการส่งซ้ำ (เฉพาะเมื่อผ่าน validation แล้ว)
            if 'processed_forms' not in session:
                session['processed_forms'] = []
            session['processed_forms'].append(form_token)
            
            # จำกัดจำนวน token ที่เก็บ
            if len(session['processed_forms']) > 20:
                session['processed_forms'] = session['processed_forms'][-20:]
            
            # สร้างข้อมูลผู้ป่วย
            patient_data = {
                'title': form.title.data,
                'calendar_name': form.calendar_name.data,
                'start_date': form.start_date.data.strftime('%Y-%m-%d'),
                'start_time': form.start_time.data.strftime('%H:%M'),
                'end_date': form.end_date.data.strftime('%Y-%m-%d'),
                'end_time': form.end_time.data.strftime('%H:%M'),
                'location': form.location.data or '',
                'who': form.who.data or '',
                'description': form.description.data or ''
            }
            
            if form.is_recurring.data:
                # สร้างนัดหมายเกิดซ้ำ
                day_mapping = {
                    'mon': 'MO', 'tue': 'TU', 'wed': 'WE', 'thu': 'TH',
                    'fri': 'FR', 'sat': 'SA', 'sun': 'SU'
                }
                
                selected_days = []
                for day_key, day_abbr in day_mapping.items():
                    if getattr(form, day_key).data:
                        selected_days.append(day_abbr)
                
                weeks = form.weeks.data or 4
                
                success, result = teamup_api.create_recurring_appointments_simple(
                    patient_data, selected_days, weeks
                )
            else:
                # สร้างนัดหมายเดี่ยว
                success, result = teamup_api.create_appointment(patient_data)
            
            if success:
                return jsonify({'success': True, 'event_id': result})
            else:
                # สร้าง form token ใหม่เมื่อเกิดข้อผิดพลาดจาก API
                new_token = str(uuid.uuid4())
                return jsonify({
                    'error': result,
                    'new_form_token': new_token
                }), 400
                
        except Exception as e:
            print(f"Exception in create_appointment: {e}")
            # สร้าง form token ใหม่เมื่อเกิด Exception
            new_token = str(uuid.uuid4())
            return jsonify({
                'error': str(e),
                'new_form_token': new_token
            }), 500
    else:
        # ส่ง validation errors กลับพร้อม form token ใหม่
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = error_list[0] if error_list else 'ข้อมูลไม่ถูกต้อง'
        
        # สร้าง form token ใหม่
        new_token = str(uuid.uuid4())
        
        return jsonify({
            'error': 'ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง',
            'field_errors': errors,
            'new_form_token': new_token
        }), 400

@app.route('/update_status', methods=['GET', 'POST'])
def update_status():
    """หน้าอัปเดตสถานะนัดหมาย"""
    if not is_api_connected():
        flash('กรุณาเชื่อมต่อ API ก่อน', 'warning')
        return redirect(url_for('setup'))
    
    event_data = None
    event_id = request.args.get('event_id', '')
    calendar_id = request.args.get('calendar_id', '')
    
    # ถ้ามี event_id ให้ดึงข้อมูลมาแสดง
    if event_id:
        try:
            response = requests.get(
                f"{teamup_api.base_url}/events/{event_id}",
                headers=teamup_api.headers
            )
            if response.status_code == 200:
                event_data = response.json()['event']
            else:
                flash(f'ไม่สามารถดึงข้อมูลนัดหมาย: {response.text}', 'danger')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
    
    if request.method == 'POST':
        try:
            post_event_id = request.form.get('event_id')
            status = request.form.get('status')
            post_calendar_id = request.form.get('calendar_id') or calendar_id
            
            if not post_event_id or not status:
                flash('กรุณากรอก Event ID และเลือกสถานะ', 'danger')
                return render_template('update_status.html', event_data=event_data, event_id=event_id)
            
            success, result = teamup_api.update_appointment_status(post_event_id, status, post_calendar_id)
            
            if success:
                flash('อัปเดตสถานะสำเร็จ', 'success')
                return redirect(url_for('appointments'))
            else:
                flash(f'การอัปเดตสถานะล้มเหลว: {result}', 'danger')
                
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
    
    return render_template('update_status.html', event_data=event_data, event_id=event_id)

@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    """หน้านำเข้าข้อมูลจากไฟล์ CSV"""
    if not is_api_connected():
        flash('กรุณาเชื่อมต่อ API ก่อน', 'warning')
        return redirect(url_for('setup'))
    
    if request.method == 'POST':
        # ตรวจสอบว่ามีไฟล์ที่อัปโหลดหรือไม่
        if 'csv_file' not in request.files:
            flash('ไม่พบไฟล์ที่อัปโหลด', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        
        # ตรวจสอบว่าผู้ใช้เลือกไฟล์หรือไม่
        if file.filename == '':
            flash('ไม่ได้เลือกไฟล์', 'danger')
            return redirect(request.url)
        
        # ตรวจสอบนามสกุลไฟล์
        if not file.filename.endswith('.csv'):
            flash('กรุณาอัปโหลดไฟล์ CSV เท่านั้น', 'danger')
            return redirect(request.url)
        
        try:
            # บันทึกไฟล์
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # นำเข้าข้อมูล
            results = teamup_api.import_from_csv(file_path)
            
            # แสดงผลลัพธ์
            flash(f"นำเข้าสำเร็จ {results['success']} รายการ, ไม่สำเร็จ {results['failed']} รายการ", 'info')
            
            # ลบไฟล์หลังจากนำเข้าเสร็จ
            os.remove(file_path)
            
            return render_template('import.html', results=results)
            
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
            return redirect(request.url)
    
    return render_template('import.html')

# เพิ่ม route สำหรับ recurring appointments
@app.route('/recurring_appointments', methods=['GET', 'POST'])
def recurring_appointments():
    """หน้าสร้างนัดหมายเกิดซ้ำ"""
    if not is_api_connected():
        flash('กรุณาเชื่อมต่อ API ก่อน', 'warning')
        return redirect(url_for('setup'))
    
    # ดึงรายการปฏิทินย่อยสำหรับ dropdown
    subcals = teamup_api.get_subcalendars()
    
    if request.method == 'POST':
        try:
            # ดึงข้อมูลจากฟอร์ม
            patient_data = {
                'title': request.form.get('title'),
                'start_date': request.form.get('start_date'),
                'start_time': request.form.get('start_time'),
                'end_date': request.form.get('end_date'),
                'end_time': request.form.get('end_time'),
                'location': request.form.get('location'),
                'who': request.form.get('who'),
                'description': request.form.get('description'),
                'calendar_name': request.form.get('calendar_name')
            }
            
            # ตรวจสอบข้อมูลที่จำเป็น
            if not patient_data['title'] or not patient_data['start_date'] or not patient_data['calendar_name']:
                flash('กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน', 'danger')
                return render_template('recurring_appointments.html', subcalendars=subcals.get('subcalendars', []))
            
            # รับค่าประเภทการเกิดซ้ำ
            recurrence_type = request.form.get('recurrence_type', 'weekly')
            
            if recurrence_type == 'weekly':
                # แมปวันในสัปดาห์
                day_mapping = {
                    'mon': 'MO', 'tue': 'TU', 'wed': 'WE', 'thu': 'TH',
                    'fri': 'FR', 'sat': 'SA', 'sun': 'SU'
                }
                
                selected_days = []
                for day_key, day_abbr in day_mapping.items():
                    if request.form.get(day_key) == 'on':
                        selected_days.append(day_abbr)
                
                weeks = int(request.form.get('weeks', 4))
                
                if not selected_days:
                    flash('กรุณาเลือกวันที่ต้องการให้เกิดซ้ำ', 'danger')
                    return render_template('recurring_appointments.html', subcalendars=subcals.get('subcalendars', []))
                
                # สร้างนัดหมายเกิดซ้ำ
                success, result = teamup_api.create_recurring_appointments_simple(
                    patient_data, selected_days, weeks
                )
                
            elif recurrence_type == 'custom':
                # รับ RRULE โดยตรง
                custom_rrule = request.form.get('custom_rrule', '')
                if not custom_rrule:
                    flash('กรุณากรอก RRULE สำหรับการเกิดซ้ำแบบกำหนดเอง', 'danger')
                    return render_template('recurring_appointments.html', subcalendars=subcals.get('subcalendars', []))
                
                success, result = teamup_api.create_recurring_appointment(patient_data, custom_rrule)
            
            if success:
                flash('สร้างนัดหมายเกิดซ้ำสำเร็จ!', 'success')
                return redirect(url_for('appointments'))
            else:
                flash(f'การสร้างนัดหมายล้มเหลว: {result}', 'danger')
                
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
    
    return render_template('recurring_appointments.html', subcalendars=subcals.get('subcalendars', []))

@app.route('/logout')
def logout():
    """ออกจากระบบและล้างการเชื่อมต่อ API"""
    global teamup_api
    teamup_api = None
    
    # ล้าง session
    session.pop('api_key', None)
    session.pop('calendar_id', None)
    
    flash('ออกจากระบบสำเร็จ', 'success')
    return redirect(url_for('index'))

def is_api_connected():
    """ตรวจสอบว่าเชื่อมต่อ API แล้วหรือไม่"""
    global teamup_api
    
    if teamup_api is None:
        # ถ้ายังไม่มี instance แต่มีข้อมูลใน session
        if 'api_key' in session and 'calendar_id' in session:
            # ลองเชื่อมต่ออีกครั้งจาก session
            try:
                teamup_api = TeamupAPI(session['api_key'], session['calendar_id'])
                success, _ = teamup_api.check_access()
                if not success:
                    teamup_api = None
            except Exception as e:
                print(f"Error reconnecting API: {e}")
                teamup_api = None
    
    return teamup_api is not None

@app.before_request
def check_api_connection():
    """ตรวจสอบการเชื่อมต่อ API ก่อนการเข้าถึงทุก route"""
    global teamup_api
    
    # ไม่ต้องตรวจสอบสำหรับ route บางอย่าง
    excluded_routes = ['static', 'setup', 'index', 'logout']
    if request.endpoint in excluded_routes:
        return
    
    # สร้าง TeamupAPI instance ถ้ายังไม่มี
    if teamup_api is None and 'api_key' in session and 'calendar_id' in session:
        teamup_api = TeamupAPI(session['api_key'], session['calendar_id'])

@app.context_processor
def inject_api_status():
    """เพิ่มตัวแปรสถานะการเชื่อมต่อ API ในทุกเทมเพลต"""
    return dict(api_connected=is_api_connected())

if __name__ == '__main__':
    app.run(debug=True)