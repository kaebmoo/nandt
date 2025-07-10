# app.py - Enhanced error handling and logging
import logging # ยังคงต้อง import เพื่อใช้ logging.getLogger
import traceback
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import uuid
import requests
import csv

# Import SaaS modules
from models import db, Organization, User, SubscriptionPlan, SubscriptionStatus, UserRole, PRICING_PLANS, UsageStat
from auth import auth_bp, login_manager
from hybrid_teamup_strategy import get_hybrid_teamup_api as get_teamup_api
from forms import AppointmentForm
from billing import billing_bp
from config import Config # ยังคงต้อง import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบเพื่อใช้งาน'
login_manager.login_message_category = 'info'

# Call Config.init_app to set up logging, create directories, etc.
Config.init_app(app) # Make sure this line is present and correctly initializing the app.


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(billing_bp)

# Create tables
with app.app_context():
    db.create_all()

# Custom exception classes
class AppointmentError(Exception):
    """Custom exception for appointment-related errors"""
    pass

class SubscriptionError(Exception):
    """Custom exception for subscription-related errors"""
    pass

class TeamUpAPIError(Exception):
    """Custom exception for TeamUp API errors"""
    pass

# Error handlers - THESE OVERRIDE THE GENERIC ONES AT THE BOTTOM
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    app.logger.warning(f'404 error: {request.url} - User: {current_user.get_id() if current_user.is_authenticated else "Anonymous"}')
    
    if request.is_json:
        return jsonify({'error': 'Resource not found'}), 404
    
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors"""
    app.logger.warning(f'403 error: {request.url} - User: {current_user.get_id() if current_user.is_authenticated else "Anonymous"}')
    
    if request.is_json:
        return jsonify({'error': 'Access forbidden'}), 403
    
    flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    
    # Log the full traceback
    app.logger.error(f'500 error: {request.url}', exc_info=True)
    
    # Log user context if available
    if current_user.is_authenticated:
        app.logger.error(f'User context: {current_user.user.id} - {current_user.user.email}')
    
    if request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    
    flash('เกิดข้อผิดพลาดของระบบ กรุณาลองอีกครั้งหรือติดต่อผู้ดูแลระบบ', 'danger')
    return render_template('errors/500.html'), 500

@app.errorhandler(AppointmentError)
def handle_appointment_error(error):
    """Handle appointment-specific errors"""
    app.logger.error(f'Appointment error: {str(error)}', exc_info=True)
    
    if request.is_json:
        return jsonify({'error': str(error)}), 400
    
    flash(f'เกิดข้อผิดพลาดกับการนัดหมาย: {str(error)}', 'danger')
    return redirect(url_for('appointments'))

@app.errorhandler(SubscriptionError)
def handle_subscription_error(error):
    """Handle subscription-specific errors"""
    app.logger.error(f'Subscription error: {str(error)}', exc_info=True)
    
    if request.is_json:
        # For subscription errors, often redirect to billing page
        return jsonify({'error': str(error), 'redirect': '/billing/choose-plan'}), 402 # 402 Payment Required
    
    flash(f'ปัญหาการสมัครสมาชิก: {str(error)}', 'warning')
    return redirect(url_for('billing.choose_plan'))

@app.errorhandler(TeamUpAPIError)
def handle_teamup_error(error):
    """Handle TeamUp API errors"""
    app.logger.error(f'TeamUp API error: {str(error)}', exc_info=True)
    
    if request.is_json:
        return jsonify({'error': 'Calendar service temporarily unavailable'}), 503 # Service Unavailable
    
    flash('เกิดข้อผิดพลาดกับระบบปฏิทิน กรุณาลองอีกครั้งในภายหลัง', 'warning')
    return redirect(url_for('index'))

# Request logging middleware
@app.before_request
def log_request_info():
    """Log request information and set start time for duration calculation"""
    g.start_time = datetime.utcnow()
    
    # Log API requests
    if request.path.startswith('/api/'):
        app.logger.info(f'API Request: {request.method} {request.path} - IP: {request.remote_addr}')
    
    # Log sensitive endpoints access
    sensitive_paths = ['/auth/', '/billing/', '/admin/']
    if any(request.path.startswith(path) for path in sensitive_paths):
        user_id = current_user.get_id() if current_user.is_authenticated else 'Anonymous'
        app.logger.info(f'Sensitive endpoint access: {request.path} - User: {user_id} - IP: {request.remote_addr}')

@app.after_request
def log_response_info(response):
    """Log response information, including request duration and errors"""
    if hasattr(g, 'start_time'):
        duration = (datetime.utcnow() - g.start_time).total_seconds()
        
        # Log slow requests
        if duration > 2.0: # 2 seconds threshold
            app.logger.warning(f'Slow request: {request.method} {request.path} - Duration: {duration:.2f}s')
        
        # Log error responses
        if response.status_code >= 400:
            user_id = current_user.get_id() if current_user.is_authenticated else 'Anonymous'
            app.logger.warning(f'Error response: {response.status_code} - {request.method} {request.path} - User: {user_id}')
    
    return response

# Context processor for error templates
@app.context_processor
def inject_error_context():
    """Inject context variables specifically for error templates"""
    return {
        'support_email': 'support@nuddee.com',
        'current_time': datetime.utcnow(),
        'user_id': current_user.get_id() if current_user.is_authenticated else None
    }

# Main application routes
@app.route('/')
def index():
    """หน้าแรกของแอปพลิเคชัน"""
    if not current_user.is_authenticated:
        # แสดงหน้า landing สำหรับผู้ที่ยังไม่ได้ login
        return render_template('landing.html', pricing_plans=PRICING_PLANS)
    
    # แสดง dashboard สำหรับผู้ที่ login แล้ว
    try:
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # ดึงสถิติการใช้งาน
        stats = teamup_api.get_organization_stats()
        
        # ดึงข้อมูลปฏิทินย่อย
        subcals = teamup_api.get_subcalendars()
        subcalendar_count = len(subcals.get('subcalendars', []))
        
        # ดึงข้อมูลการนัดหมายวันนี้
        today = datetime.now()
        start_date = datetime(today.year, today.month, today.day)
        end_date = start_date + timedelta(days=1)
        
        events = teamup_api.get_events(start_date=start_date, end_date=end_date)
        today_appointments = len(events.get('events', []))
        
        summary_data = {
            'subcalendar_count': subcalendar_count,
            'today_appointments': today_appointments,
            'subcalendars': subcals.get('subcalendars', [])[:5],
            'stats': stats
        }
        
        return render_template('dashboard.html', 
                             summary_data=summary_data,
                             organization=current_user.organization)
        
    except Exception as e:
        # Log the error and flash a message
        app.logger.error(f"Error loading dashboard for user {current_user.get_id()}: {str(e)}", exc_info=True)
        flash('เกิดข้อผิดพลาดในการโหลดข้อมูลแดชบอร์ด กรุณาลองใหม่อีกครั้ง', 'danger')
        return render_template('dashboard.html', 
                             summary_data=None,
                             organization=current_user.organization)

# เพิ่มฟังก์ชันสำหรับ Jinja2 filters
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """แปลง timestamp เป็นวันที่"""
    try:
        return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y')
    except:
        return 'ไม่ทราบ'

# เพิ่มฟังก์ชันสำหรับ context processor
@app.context_processor
def inject_global_vars():
    """เพิ่มตัวแปรสำหรับทุกเทมเพลต"""
    context = {}
    
    if current_user.is_authenticated:
        context.update({
            'current_organization': current_user.organization,
            'current_user_role': current_user.user.role,
            'subscription_status': current_user.organization.subscription_status,
            'is_trial_expired': current_user.organization.is_trial_expired(),
            'is_subscription_active': current_user.organization.is_subscription_active()
        })
    
    return context

@app.route('/appointments')
@login_required
def appointments():
    """หน้าแสดงรายการนัดหมาย"""
    try:
        # ตรวจสอบสถานะการสมัครสมาชิก
        if not current_user.organization.is_subscription_active():
            if current_user.organization.is_trial_expired():
                raise SubscriptionError('การทดลองใช้งานหมดอายุแล้ว กรุณาเลือกแพ็คเกจที่เหมาะสม')
        
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # สร้าง form
        form = AppointmentForm()
        
        # ดึงรายการปฏิทินย่อยสำหรับ dropdown
        try:
            subcals = teamup_api.get_subcalendars()
            form.calendar_name.choices = [('', 'เลือกปฏิทินย่อย')] + [
                (subcal['name'], subcal['name']) for subcal in subcals.get('subcalendars', [])
            ]
        except Exception as e:
            app.logger.error(f'Failed to get subcalendars for appointments page: {str(e)}', exc_info=True)
            raise TeamUpAPIError('Unable to load calendar options')
        
        # สร้าง unique form token
        form.form_token.data = str(uuid.uuid4())
        
        # สร้างวันที่สำหรับค่าเริ่มต้น
        today = datetime.now().strftime('%Y-%m-%d')
        next_month = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        
        # รับพารามิเตอร์ subcalendar_id จาก URL
        selected_subcalendar_id = request.args.get('subcalendar_id', '')
        
        return render_template('appointments.html', 
                              form=form,
                              subcalendars=subcals.get('subcalendars', []),
                              today=today,
                              end_date=next_month,
                              selected_subcalendar_id=selected_subcalendar_id,
                              organization=current_user.organization)
        
    except SubscriptionError as e:
        return handle_subscription_error(e)
    except TeamUpAPIError as e:
        return handle_teamup_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error on appointments page: {str(e)}', exc_info=True)
        flash('เกิดข้อผิดพลาดในการโหลดหน้านัดหมาย กรุณาลองใหม่อีกครั้ง', 'danger')
        return redirect(url_for('index'))

@app.route('/get_events')
@login_required
def get_events():
    """API endpoint for fetching events with enhanced error handling"""
    try:
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # Get parameters
        start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'))
        subcalendar_id = request.args.get('subcalendar_id', '')
        event_id = request.args.get('event_id', '')
        
        # Validate date parameters
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            # Check date range limits
            if (end_dt - start_dt).days > 365:
                return jsonify({'error': 'Date range too large (max 365 days)', 'events': []}), 400
                
        except ValueError as e:
            app.logger.warning(f'Invalid date format in get_events: {start_date_str}, {end_date_str} - {str(e)}')
            return jsonify({'error': 'Invalid date format', 'events': []}), 400
            
        if event_id:
            # Fetch specific event
            try:
                # Fetch events within a reasonable range to find the specific event
                events = teamup_api.get_events(start_date=start_dt, end_date=end_dt)
                
                target_event = None
                for event in events.get('events', []):
                    if str(event.get('id')) == str(event_id):
                        target_event = event
                        break
                
                if target_event:
                    return jsonify({'events': [target_event]})
                else:
                    return jsonify({'error': 'Event not found', 'events': []}), 404
                    
            except Exception as e:
                app.logger.error(f'Error fetching specific event {event_id}: {str(e)}', exc_info=True)
                raise TeamUpAPIError(f'Failed to fetch event: {str(e)}')
            
        # Fetch events by criteria
        try:
            subcalendar_filter = None
            if subcalendar_id:
                try:
                    subcalendar_filter = int(subcalendar_id)
                except ValueError:
                    app.logger.warning(f'Invalid subcalendar_id format: {subcalendar_id}')
                    # Continue with None if invalid, or raise error if strict validation needed
            
            events = teamup_api.get_events(
                start_date=start_dt,
                end_date=end_dt,
                subcalendar_id=subcalendar_filter
            )
            
            # Log successful fetch
            event_count = len(events.get('events', []))
            app.logger.info(f'Events fetched: {event_count} events - User: {current_user.user.id}')
            
            return jsonify(events)
            
        except Exception as e:
            app.logger.error(f'Error fetching events: {str(e)}', exc_info=True)
            raise TeamUpAPIError(f'Failed to fetch events: {str(e)}')
            
    except TeamUpAPIError as e:
        return handle_teamup_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error in get_events: {str(e)}', exc_info=True)
        return jsonify({'error': 'Unable to fetch events', 'events': []}), 500

@app.route('/create_appointment', methods=['POST'])
@login_required
def create_appointment():
    """API endpoint for creating appointments with enhanced error handling"""
    try:
        # Check subscription status
        if not current_user.organization.is_subscription_active():
            if current_user.organization.is_trial_expired():
                raise SubscriptionError('Trial period has expired. Please choose a subscription plan.')
        
        # Check usage limits
        if not current_user.organization.can_create_appointment():
            raise SubscriptionError('Monthly appointment limit reached. Please upgrade your plan.')
        
        # Create TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        form = AppointmentForm()
        
        # Get subcalendars for validation
        try:
            subcals = teamup_api.get_subcalendars()
            form.calendar_name.choices = [
                (subcal['name'], subcal['name']) for subcal in subcals.get('subcalendars', [])
            ]
        except Exception as e:
            app.logger.error(f'Failed to get subcalendars during appointment creation: {str(e)}', exc_info=True)
            raise TeamUpAPIError('Unable to access calendar service for subcalendars')
        
        if form.validate_on_submit():
            # Prevent duplicate submissions
            form_token = form.form_token.data
            if form_token and form_token in session.get('processed_forms', []):
                return jsonify({
                    'error': 'Request already processed',
                    'new_form_token': str(uuid.uuid4()) # Provide new token for subsequent tries
                }), 400
            
            # Validate recurring appointments
            if form.is_recurring.data:
                is_valid, error_msg = form.validate_recurring_days()
                if not is_valid:
                    return jsonify({
                        'error': error_msg,
                        'new_form_token': str(uuid.uuid4())
                    }), 400
            
            # Store token to prevent resubmission
            if 'processed_forms' not in session:
                session['processed_forms'] = []
            session['processed_forms'].append(form_token)
            
            # Limit stored tokens to prevent session bloat
            if len(session['processed_forms']) > 20:
                session['processed_forms'] = session['processed_forms'][-20:]
            
            # Prepare appointment data
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
            
            try:
                if form.is_recurring.data:
                    # Create recurring appointments
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
                    # Create single appointment
                    success, result = teamup_api.create_appointment(patient_data)
                
                if success:
                    # Log successful creation
                    app.logger.info(f'Appointment created: {result} - User: {current_user.user.id}')
                    
                    # Update usage statistics
                    usage_stat = UsageStat.get_or_create_today(current_user.user.organization_id)
                    usage_stat.appointments_created += 1
                    db.session.commit()
                    
                    return jsonify({'success': True, 'event_id': result})
                else:
                    raise AppointmentError(result) # Raise custom error for API failure
                    
            except Exception as e:
                app.logger.error(f'TeamUp API error during appointment creation: {str(e)}', exc_info=True)
                raise TeamUpAPIError(f'Failed to create appointment: {str(e)}') # Re-raise as TeamUpAPIError
                
        else:
            # Form validation errors
            errors = {}
            for field, error_list in form.errors.items():
                errors[field] = error_list[0] if error_list else 'Invalid data'
            
            app.logger.warning(f'Form validation failed: {errors} - User: {current_user.user.id}')
            
            return jsonify({
                'error': 'Please check your input data',
                'field_errors': errors,
                'new_form_token': str(uuid.uuid4()) # Provide new token for subsequent tries
            }), 400
            
    except SubscriptionError as e:
        return handle_subscription_error(e)
    except TeamUpAPIError as e:
        return handle_teamup_error(e)
    except AppointmentError as e:
        return handle_appointment_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error in create_appointment: {str(e)}', exc_info=True)
        return jsonify({
            'error': 'An unexpected error occurred. Please try again.',
            'new_form_token': str(uuid.uuid4())
        }), 500

@app.route('/update_status', methods=['GET', 'POST'])
@login_required
def update_status():
    """หน้าอัปเดตสถานะนัดหมาย"""
    try:
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        event_data = None
        event_id = request.args.get('event_id', '')
        calendar_id = request.args.get('calendar_id', '') # Keep this if calendar_id is needed for context
        
        # ถ้ามี event_id ให้ดึงข้อมูลมาแสดง
        if event_id:
            try:
                # Fetch events within a reasonable range to find the specific event
                # Assuming get_events can fetch a single event by ID if provided, or a range
                events_response = teamup_api.get_events(event_id=event_id)
                events_list = events_response.get('events', [])
                if events_list:
                    event_data = events_list[0] # Assuming it returns the specific event if found
                
                if not event_data:
                    flash('ไม่พบนัดหมายที่ระบุ', 'danger')
            except Exception as e:
                app.logger.error(f'Error fetching event {event_id} for update_status: {str(e)}', exc_info=True)
                flash('เกิดข้อผิดพลาดในการดึงข้อมูลนัดหมาย', 'danger')
        
        if request.method == 'POST':
            try:
                post_event_id = request.form.get('event_id')
                status = request.form.get('status')
                post_calendar_id = request.form.get('calendar_id') or calendar_id # Use posted or existing
                
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
                app.logger.error(f'Error updating appointment status: {str(e)}', exc_info=True)
                flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        
        return render_template('update_status.html', event_data=event_data, event_id=event_id)
        
    except Exception as e:
        app.logger.error(f'Unexpected error on update_status page: {str(e)}', exc_info=True)
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        return redirect(url_for('appointments'))

@app.route('/subcalendars')
@login_required
def subcalendars():
    """หน้าแสดงรายการปฏิทินย่อย"""
    try:
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # ดึงข้อมูลปฏิทินย่อย
        subcals = teamup_api.get_subcalendars()
        return render_template('subcalendars.html', subcalendars=subcals.get('subcalendars', []))
        
    except Exception as e:
        app.logger.error(f'Error fetching subcalendars: {str(e)}', exc_info=True)
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลปฏิทินย่อย: {e}', 'danger')
        return render_template('subcalendars.html', subcalendars=[])

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    """หน้านำเข้าข้อมูลจากไฟล์ CSV"""
    try:
        # ตรวจสอบสถานะการสมัครสมาชิก
        if not current_user.organization.is_subscription_active():
            if current_user.organization.is_trial_expired():
                raise SubscriptionError('การทดลองใช้งานหมดอายุแล้ว กรุณาเลือกแพ็คเกจที่เหมาะสม')
        
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
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
                # Ensure UPLOAD_FOLDER is configured in Config
                if not app.config.get('UPLOAD_FOLDER'):
                    raise RuntimeError("UPLOAD_FOLDER is not configured in app.config")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # นำเข้าข้อมูล (ต้องสร้างฟังก์ชันใหม่ใน MultiTenantTeamupAPI)
                results = import_appointments_from_csv(teamup_api, file_path)
                
                # แสดงผลลัพธ์
                flash(f"นำเข้าสำเร็จ {results['success']} รายการ, ไม่สำเร็จ {results['failed']} รายการ", 'info')
                
                # ลบไฟล์หลังจากนำเข้าเสร็จ
                os.remove(file_path)
                
                return render_template('import.html', results=results)
                
            except Exception as e:
                app.logger.error(f'Error processing CSV import: {str(e)}', exc_info=True)
                flash(f'เกิดข้อผิดพลาดในการประมวลผลไฟล์: {e}', 'danger')
                return redirect(request.url)
        
        return render_template('import.html')
        
    except SubscriptionError as e:
        return handle_subscription_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error on import page: {str(e)}', exc_info=True)
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/reports')
@login_required
def reports():
    """หน้ารายงานการใช้งาน"""
    try:
        # สร้าง TeamupAPI instance
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # ดึงสถิติการใช้งาน
        stats = teamup_api.get_organization_stats()
        
        # ดึงข้อมูล audit logs
        from models import AuditLog # Ensure AuditLog is imported
        recent_activities = AuditLog.query.filter_by(
            organization_id=current_user.user.organization_id
        ).order_by(AuditLog.created_at.desc()).limit(50).all()
        
        return render_template('reports.html', 
                             stats=stats, 
                             recent_activities=recent_activities,
                             organization=current_user.organization)
        
    except Exception as e:
        app.logger.error(f'Error loading reports page: {str(e)}', exc_info=True)
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        return redirect(url_for('index'))

# Helper Functions
def import_appointments_from_csv(teamup_api, file_path):
    """นำเข้าข้อมูลนัดหมายจาก CSV"""
    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for i, row in enumerate(reader, 1):
                try:
                    # ตรวจสอบข้อมูลที่จำเป็น
                    required_fields = ['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'Calendar Name']
                    for field in required_fields:
                        if field not in row or not row[field]:
                            raise ValueError(f"Missing required data: {field} in row {i}")
                    
                    # แปลงข้อมูลเป็นรูปแบบที่ฟังก์ชัน create_appointment ต้องการ
                    patient_data = {
                        'title': row['Subject'],
                        'start_date': row['Start Date'],
                        'start_time': row['Start Time'],
                        'end_date': row['End Date'],
                        'end_time': row['End Time'],
                        'location': row.get('Location', ''),
                        'who': row.get('Who', ''),
                        'description': row.get('Description', ''),
                        'calendar_name': row['Calendar Name']
                    }
                    
                    # สร้างนัดหมาย
                    success, result = teamup_api.create_appointment(patient_data)
                    
                    if success:
                        results['success'] += 1
                        # Update usage statistics for each successful import
                        usage_stat = UsageStat.get_or_create_today(current_user.user.organization_id)
                        usage_stat.appointments_created += 1
                        db.session.commit()
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'row': i,
                            'patient': patient_data['title'],
                            'error': result
                        })
                        
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'row': i,
                        'error': str(e)
                    })
                    app.logger.warning(f"Error importing row {i} from CSV: {str(e)}") # Log individual row errors
            
        return results
            
    except Exception as e:
        app.logger.error(f"Error reading CSV file: {e}", exc_info=True)
        results['errors'].append({
            'error': f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}"
        })
        return results

# Security logging helper
def log_security_event(event_type, details, user_id=None, ip_address=None):
    """Log security-related events to the dedicated security logger"""
    security_logger = logging.getLogger('security')
    
    log_data = {
        'event_type': event_type,
        'details': details,
        'user_id': user_id or (current_user.get_id() if current_user.is_authenticated else 'Anonymous'),
        'ip_address': ip_address or request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    security_logger.warning(f'{event_type}: {details} - Data: {log_data}')


# The original generic error handlers at the bottom are now effectively overridden
# by the more specific @app.errorhandler decorators at the top.
# Keeping them here as a fallback or for clarity, though they won't be hit for 
# 403, 404, 500, or the custom exceptions due to the explicit handlers.
# @app.errorhandler(403)
# def forbidden(error):
#     flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
#     return redirect(url_for('index'))

# @app.errorhandler(404)
# def not_found(error):
#     flash('ไม่พบหน้าที่คุณต้องการ', 'warning')
#     return redirect(url_for('index'))

# @app.errorhandler(500)
# def internal_error(error):
#     db.session.rollback()
#     flash('เกิดข้อผิดพลาดของระบบ กรุณาลองอีกครั้ง', 'danger')
#     return redirect(url_for('index'))

if __name__ == '__main__':
    # This block is typically for local development.
    # In a production WSGI environment, the app is run differently.
    app.run(debug=True)