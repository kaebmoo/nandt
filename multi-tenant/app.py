# app.py - แก้ไข TypeError ใน inject_global_vars และ subcalendarId ใน get_events

import logging
import traceback
import json
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
from flask_login import login_required, current_user, logout_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import uuid
import requests
import csv
from datetime import timezone

# Import SaaS modules
from models import db, Organization, User, SubscriptionPlan, SubscriptionStatus, UserRole, PRICING_PLANS, UsageStat
from auth import auth_bp, login_manager
from hybrid_teamup_strategy import get_hybrid_teamup_api as get_teamup_api
from forms import AppointmentForm
from billing import billing_bp
from config import Config
from api import api_bp # Ensure api_bp is imported

from flask_migrate import Migrate
# from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

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

# Request logging middleware
@app.before_request
def log_request_info():
    """Log request information and set start time for duration calculation"""
    g.start_time = datetime.now(timezone.utc)
    
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
    """เพิ่มตัวแปรสำหรับทุกเทมเพลต"""
    context = {}
    
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
        subcalendar_id_param = request.args.get('subcalendar_id', '') # Renamed to avoid confusion with filter list
        event_id = request.args.get('event_id', '')
        
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            if (end_dt - start_dt).days > 365:
                return jsonify({'error': 'Date range too large (max 365 days)', 'events': []}), 400
                
        except ValueError as e:
            app.logger.warning(f'Invalid date format in get_events: {start_date_str}, {end_date_str} - {str(e)}')
            return jsonify({'error': 'Invalid date format', 'events': []}), 400
            
        if event_id:
            events = teamup_api.get_events(event_id=event_id, start_date=start_dt, end_date=end_dt)
            
            target_event = None
            if events.get('events'):
                target_event = events['events'][0]
            
            if target_event:
                return jsonify({'events': [target_event]})
            else:
                return jsonify({'error': 'Event not found', 'events': []}), 404
                
        # **แก้ไขตรงนี้: ปรับ subcalendar_filter ให้เป็น list เสมอ**
        subcalendar_filter = [] 
        if subcalendar_id_param: # ใช้ชื่อตัวแปรใหม่
            try:
                subcalendar_filter.append(int(subcalendar_id_param)) 
            except ValueError:
                app.logger.warning(f'Invalid subcalendar_id format: {subcalendar_id_param}. Ignoring filter.')
        
        try:
            events = teamup_api.get_events(
                start_date=start_dt,
                end_date=end_dt,
                subcalendar_id=subcalendar_filter if subcalendar_filter else None # Pass None if empty list, Teamup API might prefer it
            )
            
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
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to create appointment.")
        return jsonify({'error': 'Organization data missing for user.'}), 400

    try:
        # Ensure that current_user.organization exists before accessing these properties
        org_active = current_user.organization.is_subscription_active if current_user.organization else False
        org_trial_expired = current_user.organization.is_trial_expired if current_user.organization else True

        if not org_active:
            if org_trial_expired:
                raise SubscriptionError('Trial period has expired. Please choose a subscription plan.')
        
        # current_user.organization.can_create_appointment() is a method, so () is correct here.
        if not current_user.organization.can_create_appointment():
            raise SubscriptionError('Monthly appointment limit reached. Please upgrade your plan.')
        
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        data = request.get_json()
        
        form = AppointmentForm(data=data)
        
        try:
            subcals_data = teamup_api.get_subcalendars()
            form.calendar_name.choices = [
                (subcal['name'], subcal['name']) for subcal in subcals_data.get('subcalendars', [])
            ]
        except Exception as e:
            app.logger.error(f'Failed to get subcalendars during appointment creation: {str(e)}', exc_info=True)
            raise TeamUpAPIError('Unable to access calendar service for subcalendars')
        
        if form.validate_on_submit():
            form_token = form.form_token.data
            if form_token and form_token in session.get('processed_forms', []):
                return jsonify({
                    'error': 'Request already processed',
                    'new_form_token': str(uuid.uuid4())
                }), 400
            
            if form.is_recurring.data:
                is_valid, error_msg = form.validate_recurring_days()
                if not is_valid:
                    return jsonify({
                        'error': error_msg,
                        'new_form_token': str(uuid.uuid4())
                    }), 400
            
            if 'processed_forms' not in session:
                session['processed_forms'] = []
            session['processed_forms'].append(form_token)
            
            if len(session['processed_forms']) > 20:
                session['processed_forms'] = session['processed_forms'][-20:]
            
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
                    success, result = teamup_api.create_appointment(patient_data)
                
                if success:
                    app.logger.info(f'Appointment created: {result} - User: {current_user.user.id}')
                    
                    usage_stat = UsageStat.get_or_create_today(current_user.user.organization_id)
                    usage_stat.appointments_created += 1
                    db.session.commit()
                    
                    return jsonify({'success': True, 'event_id': result})
                else:
                    raise AppointmentError(result)
                    
            except Exception as e:
                app.logger.error(f'TeamUp API error during appointment creation: {str(e)}', exc_info=True)
                raise TeamUpAPIError(f'Failed to create appointment: {str(e)}')
                
        else:
            errors = {}
            for field, error_list in form.errors.items():
                errors[field] = error_list[0] if error_list else 'Invalid data'
            
            app.logger.warning(f'Form validation failed: {errors} - User: {current_user.user.id}')
            
            return jsonify({
                'error': 'Please check your input data',
                'field_errors': errors,
                'new_form_token': str(uuid.uuid4())
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
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to update status.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index'))
    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        event_data = None
        event_id = request.args.get('event_id', '')
        calendar_id = request.args.get('calendar_id', '') # Keep this if calendar_id is needed for context
        
        if event_id:
            try:
                events_response = teamup_api.get_events(event_id=event_id, start_date=datetime.now() - timedelta(days=30), end_date=datetime.now() + timedelta(days=30))
                events_list = events_response.get('events', [])
                if events_list:
                    event_data = events_list[0]
                
                if not event_data:
                    flash('ไม่พบนัดหมายที่ระบุ', 'danger')
            except Exception as e:
                app.logger.error(f'Error fetching event {event_id} for update_status: {str(e)}', exc_info=True)
                flash('เกิดข้อผิดพลาดในการดึงข้อมูลนัดหมาย', 'danger')
        
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
                    return redirect(url_for('appointments')) # Use 'appointments' as it's directly on app
                else:
                    flash(f'การอัปเดตสถานะล้มเหลว: {result}', 'danger')
                    
            except Exception as e:
                app.logger.error(f'Error updating appointment status: {str(e)}', exc_info=True)
                flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        
        return render_template('update_status.html', event_data=event_data, event_id=event_id)
        
    except Exception as e:
        app.logger.error(f'Unexpected error on update_status page: {str(e)}', exc_info=True)
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        return redirect(url_for('appointments')) # Use 'appointments' as it's directly on app

@app.route('/subcalendars')
@login_required
def subcalendars():
    """หน้าแสดงรายการปฏิทินย่อย"""
    if not current_user.organization:
        app.logger.error(f"Error: Authenticated user {current_user.get_id()} has no associated organization trying to access subcalendars.")
        flash('ข้อมูลองค์กรไม่สมบูรณ์ กรุณาติดต่อผู้ดูแลระบบ', 'danger')
        return redirect(url_for('index')) # Use 'index' as it's directly on app
    try:
        teamup_api = get_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
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