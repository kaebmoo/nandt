# multi-tenant/app.py - แก้ไข TypeError ใน inject_global_vars และ subcalendarId ใน get_events

import logging
import traceback
import json
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g, abort
from flask_login import login_required, current_user, logout_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import uuid
import requests
import csv
from datetime import timezone

# Import SaaS modules
from models import db, cache, Organization, User, SubscriptionPlan, SubscriptionStatus, UserRole, PRICING_PLANS, UsageStat
from auth import auth_bp, login_manager
from hybrid_teamup_strategy import get_hybrid_teamup_api as get_teamup_api
from forms import AppointmentForm
from billing import billing_bp
from config import Config
from api import api_bp # Ensure api_bp is imported

from flask_migrate import Migrate
from flask_session import Session

import redis

# from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_object(Config)

# สำหรับ Flask-Session
if app.config.get('SESSION_TYPE') == 'redis':
    app.config['SESSION_KEY_PREFIX'] = 'nuddee:'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True

try:
    print("Attempting to connect to Redis...")
    # 1. สร้าง Redis client instance จาก URL ใน config
    redis_client = redis.from_url(app.config['REDIS_URL'], socket_connect_timeout=1)
    
    # 2. ทดสอบการเชื่อมต่อ
    redis_client.ping()
    
    # 3. หากสำเร็จ ให้ส่ง "อ็อบเจกต์" client นี้ไปให้ Flask-Session
    app.config['SESSION_REDIS'] = redis_client
    print("Redis connection successful. Using 'redis' for sessions.")

except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
    print("WARNING: Redis connection failed. Falling back to 'filesystem' sessions for development.")
    print("This is NOT suitable for production. Please ensure Redis is running.")
    
    # กำหนดค่าสำรองเมื่อเชื่อมต่อ Redis ไม่ได้
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['CACHE_TYPE'] = 'SimpleCache'
    
    # สร้าง Directory สำหรับเก็บไฟล์ session ถ้ายังไม่มี
    session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')
    os.makedirs(session_dir, exist_ok=True)
    app.config['SESSION_FILE_DIR'] = session_dir

# Place it after the app.config.from_object(Config) line
Session(app)

# Session configuration
app.config['SESSION_COOKIE_NAME'] = 'nuddee_session'
app.config['SESSION_COOKIE_SECURE'] = False  # True สำหรับ HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
cache.init_app(app) 

login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบเพื่อใช้งาน'
login_manager.login_message_category = 'info'

# Call Config.init_app to set up logging, create directories, etc.
Config.init_app(app)

# Register blueprints
# ไม่มี main_bp ที่นี่ เพราะ routes ใน app.py จะใช้ @app.route โดยตรง
app.register_blueprint(auth_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(api_bp) # Ensure api_bp is registered

# Create tables
# with app.app_context():
#    try:
#        # db.create_all() # Comment this out if you're using Flask-Migrate for schema management
#        # Instead, you'd typically run `flask db upgrade` from CLI
#        print("✅ Database tables created successfully")
#    except Exception as e:
#        print(f"❌ Database error: {e}")

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

# Error handlers
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
    return redirect(url_for('index')) # Use 'index' as it's directly on app

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    
    full_traceback = traceback.format_exc()
    app.logger.error(f'500 error on {request.url}\n{full_traceback}')
    
    if current_user.is_authenticated:
        if current_user.user:
            app.logger.error(f'User context: {current_user.user.id} - {current_user.user.email}')
        else:
            app.logger.error(f'User context: Authenticated user ID {current_user.get_id()} but user object is missing.')
    
    if request.is_json:
        return jsonify({'error': 'Internal server error', 'message': 'An unexpected error occurred. We have been notified.'}), 500
    
    flash('เกิดข้อผิดพลาดของระบบ กรุณาลองอีกครั้งหรือติดต่อผู้ดูแลระบบ', 'danger')
    return render_template('errors/500.html'), 500
@app.errorhandler(503)
def service_unavailable_error(error):
    """Handle 503 Service Unavailable errors"""
    return render_template('errors/503.html'), 503

@app.errorhandler(AppointmentError)
def handle_appointment_error(error):
    """Handle appointment-specific errors"""
    app.logger.error(f'Appointment error: {str(error)}', exc_info=True)
    
    if request.is_json:
        return jsonify({'error': str(error)}), 400
    
    flash(f'เกิดข้อผิดพลาดกับการนัดหมาย: {str(error)}', 'danger')
    return redirect(url_for('appointments')) # Use 'appointments' as it's directly on app

@app.errorhandler(SubscriptionError)
def handle_subscription_error(error):
    """Handle subscription-specific errors"""
    app.logger.error(f'Subscription error: {str(error)}', exc_info=True)
    
    if request.is_json:
        return jsonify({'error': str(error), 'redirect': '/billing/choose-plan'}), 402
    
    flash(f'ปัญหาการสมัครสมาชิก: {str(error)}', 'warning')
    return redirect(url_for('billing.choose_plan'))

@app.errorhandler(TeamUpAPIError)
def handle_teamup_error(error):
    """Handle TeamUp API errors"""
    app.logger.error(f'TeamUp API error: {str(error)}', exc_info=True)
    
    if request.is_json:
        return jsonify({'error': 'Calendar service temporarily unavailable'}), 503
    
    flash('เกิดข้อผิดพลาดกับระบบปฏิทิน กรุณาลองอีกครั้งในภายหลัง', 'warning')
    return redirect(url_for('index')) # Use 'index' as it's directly on app

@app.before_request
def before_request_handler():
    # --- ส่วนที่ 1: ตั้งค่า g object ---
    g.start_time = datetime.now(timezone.utc)

    # --- ส่วนที่ 2: Health Check (เฉพาะเมื่อใช้ Redis) ---
    # ตรวจสอบเฉพาะ request ที่ไม่ใช่ไฟล์ static หรือหน้า debugger
    endpoint = request.endpoint
    if endpoint and ('static' not in endpoint and '__debugger__' not in endpoint):
        # Health Check นี้จำเป็นก็ต่อเมื่อเรากำหนดค่าให้ใช้ Redis เท่านั้น
        if app.config.get('SESSION_TYPE') == 'redis':
            try:
                # ดึง Redis client จาก Flask-Session extension
                redis_client = app.session_interface.client
                redis_client.ping()
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                # หากเชื่อมต่อ Redis ไม่ได้ ให้หยุดการทำงานและส่งหน้า 503
                app.logger.critical(f"Redis connection failed while app was running: {e}")
                abort(503)

    # --- ส่วนที่ 3: บันทึก Log ---
    # Log API requests
    if request.path.startswith('/api/'):
        app.logger.info(f'API Request: {request.method} {request.path} - IP: {request.remote_addr}')
    
    # Log sensitive endpoints access
    sensitive_paths = ['/auth/', '/billing/', '/admin/']
    if any(request.path.startswith(path) for path in sensitive_paths):
        user_id = current_user.get_id() if current_user.is_authenticated else 'Anonymous'
        app.logger.info(f'Sensitive endpoint access: {request.path} - User: {user_id} - IP: {request.remote_addr}')
    
    # เพิ่มการตรวจสอบ session validity
    if current_user.is_authenticated:
        # ตรวจสอบว่า user ยังมีอยู่ในระบบหรือไม่
        if hasattr(current_user, 'user') and not current_user.user:
            logout_user()
            session.clear()
            flash('Session expired. Please login again.', 'info')
            return redirect(url_for('auth.login'))

@app.after_request
def log_response_info(response):
    """Log response information, including request duration and errors"""
    if hasattr(g, 'start_time'):
        duration = (datetime.now(timezone.utc) - g.start_time).total_seconds()
        
        # Log slow requests
        if duration > 2.0:
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
        'current_time': datetime.now(timezone.utc),
        'user_id': current_user.get_id() if current_user.is_authenticated else None
    }

# เพิ่มฟังก์ชันสำหรับ context processor
@app.context_processor
def inject_global_vars():
    """เพิ่มตัวแปรสำหรับทุกเทมเพลต - รวม timezone"""
    from datetime import timezone  # เพิ่ม import นี้
    
    context = {
        'datetime': datetime,
        'timezone': timezone,  # **เพิ่มบรรทัดนี้**
        'timedelta': timedelta  # เพิ่มด้วยเผื่อใช้
    }
    
    if current_user.is_authenticated and current_user.user:
        org = current_user.organization
        context.update({
            'current_organization': org,
            'current_user_role': current_user.user.role,
            'subscription_status': org.subscription_status if org else None,
            'is_trial_expired': org.is_trial_expired if org else True, 
            'is_subscription_active': org.is_subscription_active if org else False,
            'UserRole': UserRole,
            'SubscriptionStatus': SubscriptionStatus,
            'datetime': datetime
            # ถ้าต้องการ get_current_month_usage ที่นี่ ต้องเรียกเป็น method
            # 'current_month_usage': org.get_current_month_usage() if org else 0
        })
    
    return context

# เพิ่มฟังก์ชันสำหรับ Jinja2 filters
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """แปลง timestamp เป็นวันที่"""
    try:
        return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y')
    except:
        return 'ไม่ทราบ'

# Main application routes
@app.route('/')
def index():
    """หน้าแรกของแอปพลิเคชัน"""
    print(f"DEBUG: Index route called, authenticated: {current_user.is_authenticated}")
    
    if not current_user.is_authenticated:
        print("DEBUG: User not authenticated, showing landing page")
        return render_template('landing.html', pricing_plans=PRICING_PLANS)
    
    print("DEBUG: User authenticated, showing dashboard")
    if not current_user.organization: # Added check for user.organization here
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        logout_user() # Force logout if organization is missing
        return redirect(url_for('auth.login'))

    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        stats = teamup_api.get_organization_stats()
        
        subcals = teamup_api.get_subcalendars()
        subcalendar_count = len(subcals.get('subcalendars', []))
        
        today = datetime.now()
        start_date = datetime(today.year, today.month, today.day)
        end_date = start_date + timedelta(days=1)
        
        events = teamup_api.get_events(start_date=start_date, end_date=end_date)
        today_appointments = len(events.get('events', []))

        # Calculate days_left here in Python
        days_left_trial = None
        if current_user.organization.subscription_status == SubscriptionStatus.TRIAL and \
           current_user.organization.trial_ends_at:
            # Ensure trial_ends_at is timezone-aware for comparison if it comes from DB as naive
            # If models.py is fixed and db is migrated, it should be aware.
            # Otherwise, use .replace(tzinfo=timezone.utc)
            trial_ends_aware = current_user.organization.trial_ends_at
            if trial_ends_aware.tzinfo is None: # Fallback for old naive data
                trial_ends_aware = trial_ends_aware.replace(tzinfo=timezone.utc)

            days_left_trial = (trial_ends_aware - datetime.now(timezone.utc)).days
            if days_left_trial < 0: # Ensure it doesn't show negative days if expired
                days_left_trial = 0
        
        summary_data = {
            'subcalendar_count': subcalendar_count,
            'today_appointments': today_appointments,
            'subcalendars': subcals.get('subcalendars', [])[:5],
            'stats': stats,
            'days_left_trial': days_left_trial # Pass this to template
        }
        
        return render_template('dashboard.html', 
                             summary_data=summary_data,
                             organization=current_user.organization,
                             days_left_trial=days_left_trial # Pass explicitly as well for consistency
                            )
        
    except Exception as e:
        app.logger.error(f"Error loading dashboard for user {current_user.get_id()}: {str(e)}", exc_info=True)
        print(f"DEBUG: Dashboard error: {e}")
        flash('เกิดข้อผิดพลาดในการโหลดข้อมูลแดชบอร์ด กรุณาลองใหม่อีกครั้ง', 'danger')
        return render_template('dashboard.html', 
                             summary_data=None,
                             organization=current_user.organization)

@app.route('/appointments')
@login_required
def appointments():
    """หน้าแสดงรายการนัดหมาย"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to access appointments.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index'))
        
    try:
        # Note: is_subscription_active and is_trial_expired are properties, not methods.
        # Ensure that current_user.organization exists before accessing these properties
        org_active = current_user.organization.is_subscription_active if current_user.organization else False
        org_trial_expired = current_user.organization.is_trial_expired if current_user.organization else True

        if not org_active:
            if org_trial_expired:
                raise SubscriptionError('การทดลองใช้งานหมดอายุแล้ว กรุณาเลือกแพ็คเกจที่เหมาะสม')
        
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        form = AppointmentForm()
        
        try:
            subcals = teamup_api.get_subcalendars()
            form.calendar_name.choices = [('', 'เลือกปฏิทินย่อย')] + [
                (subcal['name'], subcal['name']) for subcal in subcals.get('subcalendars', [])
            ]
        except Exception as e:
            app.logger.error(f'Failed to get subcalendars for appointments page: {str(e)}', exc_info=True)
            raise TeamUpAPIError('Unable to load calendar options')
        
        form.form_token.data = str(uuid.uuid4())
        
        today = datetime.now().strftime('%Y-%m-%d')
        next_month = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        
        selected_subcalendar_id = request.args.get('subcalendar_id', '')
        
        return render_template('appointments.html', 
                              form=form,
                              subcalendars=subcals.get('subcalendars', []),
                              today=today,
                              end_date=next_month,
                              selected_subcalendar_id=selected_subcalendar_id,
                              organization=current_user.organization, # Pass organization for template checks
                              is_subscription_active=org_active, # Pass explicitly
                              is_trial_expired=org_trial_expired # Pass explicitly
                              )
        
    except SubscriptionError as e:
        return handle_subscription_error(e)
    except TeamUpAPIError as e:
        return handle_teamup_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error on appointments page: {str(e)}', exc_info=True)
        flash('เกิดข้อผิดพลาดในการโหลดหน้านัดหมาย กรุณาลองใหม่อีกครั้ง', 'danger')
        return redirect(url_for('index'))

# แก้ไขฟังก์ชัน get_events ใน app.py (บรรทัดประมาณ 395-480)

@app.route('/get_events')
@login_required
def get_events():
    """API endpoint for fetching events with enhanced error handling"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to get events.")
        return jsonify({'error': 'Organization data missing for user.'}), 400

    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'))
        subcalendar_id_param = request.args.get('subcalendar_id', '')
        event_id = request.args.get('event_id', '')
        
        app.logger.info(f"get_events called with params: start_date={start_date_str}, end_date={end_date_str}, subcalendar_id={subcalendar_id_param}, event_id={event_id}")
        
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            if (end_dt - start_dt).days > 365:
                return jsonify({'error': 'Date range too large (max 365 days)', 'events': []}), 400
                
        except ValueError as e:
            app.logger.warning(f'Invalid date format in get_events: {start_date_str}, {end_date_str} - {str(e)}')
            return jsonify({'error': 'Invalid date format', 'events': []}), 400
            
        # จัดการกรณีที่ต้องการ event เฉพาะ
        if event_id:
            events = teamup_api.get_events(event_id=event_id, start_date=start_dt, end_date=end_dt)
            
            target_event = None
            if events.get('events'):
                target_event = events['events'][0]
            
            if target_event:
                app.logger.info(f"Found specific event {event_id}: {target_event.get('title', 'No title')}")
                return jsonify({'events': [target_event]})
            else:
                app.logger.warning(f"Event {event_id} not found")
                return jsonify({'error': 'Event not found', 'events': []}), 404
                
        # **แก้ไขสำคัญ: จัดการ subcalendar_filter อย่างเหมาะสม**
        subcalendar_filter = None  # เริ่มต้นด้วย None
        
        if subcalendar_id_param and subcalendar_id_param.strip():
            try:
                # แปลงเป็น integer และใส่ใน list
                subcalendar_filter = [int(subcalendar_id_param.strip())]
                app.logger.info(f"Using subcalendar filter: {subcalendar_filter}")
            except ValueError:
                app.logger.warning(f'Invalid subcalendar_id format: {subcalendar_id_param}. Ignoring filter.')
                subcalendar_filter = None
        
        try:
            # เรียก TeamUp API พร้อมพารามิเตอร์ที่ถูกต้อง
            events = teamup_api.get_events(
                start_date=start_dt,
                end_date=end_dt,
                subcalendar_id=subcalendar_filter  # ส่งเป็น list หรือ None
            )
            
            # ตรวจสอบและปรับปรุงข้อมูล events ก่อนส่งกลับ
            if events.get('events'):
                for event in events['events']:
                    # ตรวจสอบว่ามี id หรือไม่
                    if 'id' not in event or not event['id']:
                        app.logger.warning(f"Event missing ID: {event}")
                        continue
                    
                    # เพิ่มข้อมูลเสริมสำหรับการแสดงผล
                    if not event.get('location'):
                        event['location'] = ''
                    if not event.get('who'):
                        event['who'] = ''
                    if not event.get('notes'):
                        event['notes'] = ''
                    
                    # แก้ไขการแสดงชื่อปฏิทินย่อย
                    if not event.get('subcalendar_display') and not event.get('subcalendar_name'):
                        if event.get('subcalendar_id'):
                            event['subcalendar_display'] = f"ปฏิทิน {event['subcalendar_id']}"
                        elif event.get('subcalendar_ids') and len(event['subcalendar_ids']) > 0:
                            event['subcalendar_display'] = f"ปฏิทิน {event['subcalendar_ids'][0]}"
                        else:
                            event['subcalendar_display'] = 'ไม่ระบุปฏิทิน'
            
            event_count = len(events.get('events', []))
            app.logger.info(f'Events fetched successfully: {event_count} events - User: {current_user.user.id} - Filter: {subcalendar_filter}')
            
            # Log สำหรับ debug เมื่อมีปัญหา
            if subcalendar_filter and event_count == 0:
                app.logger.warning(f'No events found for subcalendar filter {subcalendar_filter}. Check if subcalendar exists.')
            
            return jsonify(events)
            
        except Exception as e:
            app.logger.error(f'Error fetching events from TeamUp API: {str(e)}', exc_info=True)
            raise TeamUpAPIError(f'Failed to fetch events: {str(e)}')
            
    except TeamUpAPIError as e:
        return handle_teamup_error(e)
    except Exception as e:
        app.logger.error(f'Unexpected error in get_events: {str(e)}', exc_info=True)
        return jsonify({'error': 'Unable to fetch events', 'events': []}), 500

@app.route('/create_appointment', methods=['POST'])
@login_required
def create_appointment():
    """API endpoint for creating appointments with enhanced validation and error handling"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to create appointment.")
        return jsonify({'error': 'Organization data missing for user.'}), 400

    try:
        # ตรวจสอบ subscription status
        org_active = current_user.organization.is_subscription_active if current_user.organization else False
        org_trial_expired = current_user.organization.is_trial_expired if current_user.organization else True

        if not org_active:
            if org_trial_expired:
                raise SubscriptionError('Trial period has expired. Please choose a subscription plan.')
        
        if not current_user.organization.can_create_appointment():
            raise SubscriptionError('Monthly appointment limit reached. Please upgrade your plan.')
        
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # **แก้ไข: จัดการข้อมูลที่รับเข้ามาให้รองรับทั้ง JSON และ Form Data**
        data = None
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = request.get_json()
            if data is None:
                app.logger.error("Failed to parse JSON data despite JSON Content-Type")
                return jsonify({
                    'error': 'Invalid JSON data',
                    'new_form_token': str(uuid.uuid4())
                }), 400
        else:
            # Handle form data
            app.logger.info(f"Handling form data with Content-Type: {content_type}")
            data = {}
            for key in request.form.keys():
                value = request.form.get(key)
                # Convert string 'true'/'false' to boolean for form data
                if value in ('true', 'True'):
                    data[key] = True
                elif value in ('false', 'False'):
                    data[key] = False
                else:
                    data[key] = value
            
            app.logger.info(f"Form data received: {data}")
        
        if not data:
            return jsonify({
                'error': 'No data received',
                'new_form_token': str(uuid.uuid4())
            }), 400
        
        # **สร้าง form และ validate**
        form = AppointmentForm(data=data)
        
        try:
            subcals_data = teamup_api.get_subcalendars()
            form.calendar_name.choices = [
                (subcal['name'], subcal['name']) for subcal in subcals_data.get('subcalendars', [])
            ]
        except Exception as e:
            app.logger.error(f'Failed to get subcalendars during appointment creation: {str(e)}', exc_info=True)
            raise TeamUpAPIError('Unable to access calendar service for subcalendars')
        
        # **ตรวจสอบ CSRF และ form token**
        form_token = form.form_token.data
        if form_token and form_token in session.get('processed_forms', []):
            return jsonify({
                'error': 'Request already processed',
                'new_form_token': str(uuid.uuid4())
            }), 400
        
        # **Validate form**
        if not form.validate_on_submit():
            errors = {}
            for field, error_list in form.errors.items():
                errors[field] = error_list[0] if error_list else 'Invalid data'
            
            app.logger.warning(f'Form validation failed: {errors} - User: {current_user.user.id}')
            
            return jsonify({
                'error': 'Please check your input data',
                'field_errors': errors,
                'new_form_token': str(uuid.uuid4())
            }), 400
        
        # **เพิ่ม: ตรวจสอบ appointment logic**
        logic_valid, logic_errors = form.validate_appointment_logic()
        if not logic_valid:
            app.logger.warning(f'Appointment logic validation failed: {logic_errors} - User: {current_user.user.id}')
            return jsonify({
                'error': 'Please check your appointment settings',
                'logic_errors': logic_errors,
                'new_form_token': str(uuid.uuid4())
            }), 400
        
        # **เพิ่ม: ตรวจสอบ recurring validation**
        if form.is_recurring.data:
            is_valid, error_msg = form.validate_recurring_days()
            if not is_valid:
                return jsonify({
                    'error': error_msg,
                    'new_form_token': str(uuid.uuid4())
                }), 400
        
        # **จัดการ form token เพื่อป้องกัน double submit**
        if 'processed_forms' not in session:
            session['processed_forms'] = []
        session['processed_forms'].append(form_token)
        
        if len(session['processed_forms']) > 20:
            session['processed_forms'] = session['processed_forms'][-20:]
        
        # **ใช้ form.to_dict() เพื่อแปลงข้อมูลและ auto-correct**
        try:
            patient_data = form.to_dict()
            app.logger.info(f'Patient data prepared: {patient_data}')
        except ValidationError as e:
            return jsonify({
                'error': str(e),
                'new_form_token': str(uuid.uuid4())
            }), 400
        
        # **สร้าง appointment**
        try:
            if form.is_recurring.data:
                # สร้าง recurring appointment
                day_mapping = {
                    'mon': 'MO', 'tue': 'TU', 'wed': 'WE', 'thu': 'TH',
                    'fri': 'FR', 'sat': 'SA', 'sun': 'SU'
                }
                
                selected_days = []
                for day_key, day_abbr in day_mapping.items():
                    if patient_data['recurring_days'].get(day_key):
                        selected_days.append(day_abbr)
                
                weeks = patient_data['weeks'] or 4
                
                success, result = teamup_api.create_recurring_appointments_simple(
                    patient_data, selected_days, weeks
                )
            else:
                # สร้าง single appointment
                success, result = teamup_api.create_appointment(patient_data)
            
            if success:
                app.logger.info(f'Appointment created successfully: {result} - User: {current_user.user.id}')
                
                # อัปเดต usage statistics
                usage_stat = UsageStat.get_or_create_today(current_user.user.organization_id)
                usage_stat.appointments_created += 1
                db.session.commit()
                
                return jsonify({
                    'success': True, 
                    'event_id': result,
                    'message': 'นัดหมายถูกสร้างเรียบร้อยแล้ว'
                })
            else:
                raise AppointmentError(result)
                
        except Exception as e:
            app.logger.error(f'TeamUp API error during appointment creation: {str(e)}', exc_info=True)
            raise TeamUpAPIError(f'Failed to create appointment: {str(e)}')
            
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
    """หน้าอัปเดตสถานะนัดหมาย (เวอร์ชันปรับปรุง)"""
    if not current_user.organization:
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index'))

    teamup_api = get_teamup_api(
        organization_id=current_user.user.organization_id,
        user_id=current_user.user.id
    )
    event_id = request.args.get('event_id', '')
    event_data = None

    if event_id:
        try:
            # ดึงข้อมูลล่าสุดของ event เพื่อแสดงในฟอร์ม
            response = teamup_api.get_events(event_id=event_id)
            if response.get('events'):
                event_data = response['events'][0]
            else:
                flash('ไม่พบนัดหมายที่ระบุ', 'danger')
        except Exception as e:
            flash(f'ไม่สามารถดึงข้อมูลนัดหมายได้: {e}', 'danger')
    
    if request.method == 'POST':
        post_event_id = request.form.get('event_id')
        status = request.form.get('status')
        
        if not post_event_id or not status:
            flash('ข้อมูลไม่ครบถ้วน', 'danger')
            return render_template('update_status.html', event_data=event_data, event_id=event_id)
        
        try:
            # เรียกฟังก์ชันที่แก้ไขแล้วใน strategy ซึ่งจัดการความซับซ้อนทั้งหมด
            success, result = teamup_api.update_appointment_status(post_event_id, status)
            
            if success:
                app.logger.info(f'Status updated successfully for event {post_event_id} to {status} by user {current_user.user.id}')
                flash(f'อัปเดตสถานะเป็น "{status}" สำเร็จ', 'success')
                return redirect(url_for('appointments'))
            else:
                app.logger.warning(f'Failed to update status for event {post_event_id}: {result}')
                flash(f'การอัปเดตสถานะล้มเหลว: {result}', 'danger')
                
        except Exception as e:
            app.logger.error(f'Error updating appointment status: {str(e)}', exc_info=True)
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return render_template('update_status.html', event_data=event_data, event_id=event_id)

@app.route('/subcalendars')
@login_required  
def subcalendars():
    """หน้าแสดงรายการปฏิทินย่อย"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to access subcalendars.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index'))
    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        subcals_data = teamup_api.get_subcalendars()
        subcals_list = subcals_data.get('subcalendars', [])
        
        # **เพิ่ม Debug ที่ละเอียดขึ้น**
        print(f"DEBUG: subcals_data type: {type(subcals_data)}")
        print(f"DEBUG: subcals_data content: {subcals_data}")
        print(f"DEBUG: subcals_list type: {type(subcals_list)}")
        print(f"DEBUG: subcals_list length: {len(subcals_list)}")
        
        if subcals_list:
            print(f"DEBUG: First item type: {type(subcals_list[0])}")
            print(f"DEBUG: First item content: {subcals_list[0]}")
            if hasattr(subcals_list[0], '__dict__'):
                print(f"DEBUG: First item __dict__: {subcals_list[0].__dict__}")
        
        return render_template('subcalendars.html', subcalendars=subcals_list)
        
    except Exception as e:
        app.logger.error(f'Error fetching subcalendars: {str(e)}', exc_info=True)
        print(f"DEBUG: Exception in subcalendars route: {e}")
        import traceback
        traceback.print_exc()
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลปฏิทินย่อย: {e}', 'danger')
        return render_template('subcalendars.html', subcalendars=[])

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    """หน้านำเข้าข้อมูลจากไฟล์ CSV"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to access import.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index')) # Use 'index' as it's directly on app
    try:
        if not current_user.organization.is_subscription_active:
            if current_user.organization.is_trial_expired:
                raise SubscriptionError('การทดลองใช้งานหมดอายุแล้ว กรุณาเลือกแพ็คเกจที่เหมาะสม')
        
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        if request.method == 'POST':
            if 'csv_file' not in request.files:
                flash('ไม่พบไฟล์ที่อัปโหลด', 'danger')
                return redirect(request.url)
            
            file = request.files['csv_file']
            
            if file.filename == '':
                flash('ไม่ได้เลือกไฟล์', 'danger')
                return redirect(request.url)
            
            if not file.filename.endswith('.csv'):
                flash('กรุณาอัปโหลดไฟล์ CSV เท่านั้น', 'danger')
                return redirect(request.url)
            
            try:
                filename = secure_filename(file.filename)
                if not app.config.get('UPLOAD_FOLDER'):
                    raise RuntimeError("UPLOAD_FOLDER is not configured in app.config")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                results = import_appointments_from_csv(teamup_api, file_path)
                
                flash(f"นำเข้าสำเร็จ {results['success']} รายการ, ไม่สำเร็จ {results['failed']} รายการ", 'info')
                
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
        return redirect(url_for('index')) # Use 'index' as it's directly on app

@app.route('/reports')
@login_required
def reports():
    """หน้ารายงานการใช้งาน"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to access reports.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index')) # Use 'index' as it's directly on app
    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        stats = teamup_api.get_organization_stats()
        
        from models import AuditLog
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
        return redirect(url_for('index')) # Use 'index' as it's directly on app

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
                    required_fields = ['Subject', 'Start Date', 'Start Time', 'End Date', 'End Time', 'Calendar Name']
                    for field in required_fields:
                        if field not in row or not row[field]:
                            raise ValueError(f"Missing required data: {field} in row {i}")
                    
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
                    
                    success, result = teamup_api.create_appointment(patient_data)
                    
                    if success:
                        results['success'] += 1
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
                    app.logger.warning(f"Error importing row {i} from CSV: {str(e)}")
            
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
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    security_logger.warning(f'{event_type}: {details} - Data: {log_data}')

if __name__ == '__main__':
    app.run(debug=True)