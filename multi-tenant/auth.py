# auth.py - Security Improvements

from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template, current_app, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash
import secrets
import pyotp
import qrcode
import io
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from datetime import datetime, timedelta
import uuid
import os
import requests
import re # Added for input validation
from datetime import timezone
from functools import wraps # Added for decorator
import hashlib # Added for HMAC (though not used in provided snippet, good for security)
import hmac # Added for HMAC (though not used in provided snippet, good for security)
import json
import redis

from models import db, User, Organization, SubscriptionPlan, SubscriptionStatus, UserRole, PRICING_PLANS

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
login_manager = LoginManager()

try:
    redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
except:
    # Fallback ถ้าไม่มี Redis
    redis_client = None
    print("Warning: Redis not available, using in-memory cache for idempotency")
    _memory_cache = {}

def get_request_fingerprint(data):
    """สร้าง fingerprint สำหรับ request เพื่อใช้ใน idempotency check"""
    # เอาเฉพาะข้อมูลสำคัญที่ไม่เปลี่ยนแปลง
    key_data = {
        'email': data.get('email', '').lower().strip(),
        'organization_name': data.get('organization_name', '').strip(),
        'contact_email': data.get('contact_email', '').lower().strip()
    }
    
    data_str = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def check_idempotency(request_id, fingerprint, ttl_seconds=300):
    """ตรวจสอบว่า request นี้เคยถูกประมวลผลแล้วหรือไม่"""
    try:
        if redis_client:
            # ใช้ Redis
            key = f"idempotency:{fingerprint}"
            existing = redis_client.get(key)
            if existing:
                return json.loads(existing)
            return None
        else:
            # ใช้ memory cache
            key = f"idempotency:{fingerprint}"
            if key in _memory_cache:
                entry = _memory_cache[key]
                # ตรวจสอบ expiry
                if datetime.now(timezone.utc) < entry['expires_at']:
                    return entry['response']
                else:
                    del _memory_cache[key]
            return None
    except Exception as e:
        print(f"Error checking idempotency: {e}")
        return None

def store_idempotency_result(request_id, fingerprint, response_data, ttl_seconds=300):
    """เก็บผลลัพธ์ของ request เพื่อใช้ใน idempotency"""
    try:
        result = {
            'request_id': request_id,
            'response': response_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if redis_client:
            key = f"idempotency:{fingerprint}"
            redis_client.setex(key, ttl_seconds, json.dumps(result))
        else:
            # ใช้ memory cache
            key = f"idempotency:{fingerprint}"
            _memory_cache[key] = {
                'response': response_data,
                'expires_at': datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            }
            
            # ทำความสะอาด expired entries
            current_time = datetime.now(timezone.utc)
            expired_keys = [k for k, v in _memory_cache.items() 
                          if v.get('expires_at', current_time) < current_time]
            for key in expired_keys:
                del _memory_cache[key]
                
    except Exception as e:
        print(f"Error storing idempotency result: {e}")

# เพิ่ม decorator สำหรับ idempotency
def idempotent_registration(f):
    """Decorator สำหรับป้องกัน duplicate registration requests"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method != 'POST':
            return f(*args, **kwargs)
            
        try:
            data = request.get_json() if request.is_json else dict(request.form)
            
            # ดึง request ID และสร้าง fingerprint
            request_id = request.headers.get('X-Request-ID') or data.get('request_id')
            fingerprint = get_request_fingerprint(data)
            
            if not request_id:
                # ถ้าไม่มี request ID ให้สร้างใหม่
                request_id = f"auto_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            
            # ตรวจสอบ idempotency
            existing_result = check_idempotency(request_id, fingerprint)
            if existing_result:
                print(f"Returning cached result for request {request_id}")
                cached_response = existing_result['response']
                return jsonify(cached_response), 200 if cached_response.get('success') else 400
            
            # เรียกใช้ function ปกติ
            result = f(*args, **kwargs)
            
            # เก็บผลลัพธ์สำหรับ idempotency (เฉพาะ successful response)
            if hasattr(result, 'status_code') and result.status_code == 200:
                try:
                    response_data = result.get_json()
                    store_idempotency_result(request_id, fingerprint, response_data)
                except:
                    pass  # ไม่สำคัญถ้าเก็บไม่ได้
            
            return result
            
        except Exception as e:
            print(f"Error in idempotent_registration decorator: {e}")
            # ถ้า idempotency ระบบล้มเหลว ให้ทำงานปกติ
            return f(*args, **kwargs)
    
    return decorated_function

# Rate limiting store (in production, use Redis or a proper database)
failed_attempts = {}

def rate_limit_check(identifier, max_attempts=5, window_minutes=15):
    """
    Check if an identifier (e.g., IP address or email) is rate limited.
    Prevents brute-force attacks by limiting failed attempts within a time window.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    
    if identifier in failed_attempts:
        # Clean old attempts that are outside the window
        failed_attempts[identifier] = [
            attempt for attempt in failed_attempts[identifier] 
            if attempt > window_start
        ]
        
        # Check if the number of attempts exceeds the maximum allowed
        if len(failed_attempts[identifier]) >= max_attempts:
            return False # Rate limited
    
    return True # Not rate limited

def record_failed_attempt(identifier):
    """
    Record a failed attempt for a given identifier.
    Used in conjunction with rate_limit_check.
    """
    if identifier not in failed_attempts:
        failed_attempts[identifier] = []
    failed_attempts[identifier].append(datetime.now(timezone.utc))

def validate_input(data, required_fields, optional_fields=None):
    """
    Validate and sanitize input data from request.
    Ensures all required fields are present and sanitizes string inputs.
    """
    if optional_fields is None:
        optional_fields = []
    
    errors = []
    sanitized = {}
    
    # Check required fields
    for field in required_fields:
        if field not in data or not data[field]:
            errors.append(f'{field} is required')
        else:
            sanitized[field] = sanitize_input(data[field])
    
    # Add optional fields if present and sanitize them
    for field in optional_fields:
        if field in data and data[field]:
            sanitized[field] = sanitize_input(data[field])
    
    return sanitized, errors

def sanitize_input(value):
    """
    Sanitize string input to prevent XSS (Cross-Site Scripting) attacks.
    Removes common script tags and javascript: URIs.
    """
    if isinstance(value, str):
        # Remove potential XSS patterns
        value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
        value = value.strip() # Remove leading/trailing whitespace
    return value

def validate_email(email):
    """
    Validate email format using a regular expression.
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password_strength(password):
    """
    Validate password strength based on common criteria:
    - Minimum length (8 characters)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    # Optional: Add special character check if desired
    # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
    #     return False, "Password must contain at least one special character"
    
    return True, "Password is strong"

def require_admin(f):
    """
    Decorator to restrict access to admin users only.
    Redirects to login if not authenticated, or to index with an error if not admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Ensure current_user.user is loaded before checking role
        if not current_user.user:
            flash('User data not found. Please re-login.', 'danger')
            logout_user()
            return redirect(url_for('auth.login'))

        if current_user.user.role != UserRole.ADMIN:
            flash('Access denied. Admin role required.', 'danger')
            return redirect(url_for('index')) # Assuming 'index' is your main dashboard
        
        return f(*args, **kwargs)
    return decorated_function

# User class for Flask-Login
class AuthUser(UserMixin):
    def __init__(self, user_id):
        self.id = user_id
        self._user_instance = None

    @property
    def user(self):
        from flask import current_app
        from models import db, User # Import db and User

        if self._user_instance is None or self._user_instance.id != self.id:
            with current_app.app_context():
                from sqlalchemy.orm import joinedload
                self._user_instance = User.query.options(joinedload(User.organization)).get(self.id)
                
        return self._user_instance
    
    def get_id(self):
        return str(self.id)
    
    @property
    def organization(self):
        return self.user.organization if self.user else None

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(user_id)
    if user and user.is_active:
        return AuthUser(user.id)
    return None

# ปรับปรุง registration route ด้วย idempotency protection
@auth_bp.route('/register', methods=['GET', 'POST'])
@idempotent_registration  # เพิ่ม decorator นี้
def register():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            required_fields = ['email', 'password', 'first_name', 'last_name', 'organization_name', 'contact_email']
            optional_fields = ['phone', 'address', 'confirm_password']
            
            sanitized_data, validation_errors = validate_input(data, required_fields, optional_fields)
            
            if validation_errors:
                errors_dict = {field: "This field is required" for field in validation_errors}
                return jsonify({'error': 'Validation failed', 'field_errors': errors_dict}), 400
            
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if not rate_limit_check(client_ip):
                return jsonify({'error': 'Too many registration attempts. Please try again later.'}), 429
            
            if not validate_email(sanitized_data['email']):
                record_failed_attempt(client_ip)
                return jsonify({'error': 'Invalid email format', 'field_errors': {'email': 'Invalid email format'}}), 400
            
            # ตรวจสอบ email ที่มีอยู่แล้วก่อนทำอะไร
            existing_user = User.query.filter_by(email=sanitized_data['email']).first()
            if existing_user:
                record_failed_attempt(client_ip)
                return jsonify({'error': 'Email already registered', 'field_errors': {'email': 'Email already registered'}}), 400
            
            is_strong, message = validate_password_strength(sanitized_data['password'])
            if not is_strong:
                record_failed_attempt(client_ip)
                return jsonify({'error': message, 'field_errors': {'password': message}}), 400
            
            if 'confirm_password' in sanitized_data:
                if sanitized_data['password'] != sanitized_data['confirm_password']:
                    record_failed_attempt(client_ip)
                    return jsonify({'error': 'Passwords do not match', 'field_errors': {'confirm_password': 'Passwords do not match'}}), 400
            
            # เริ่ม database transaction
            with db.session.begin():  # ใช้ context manager เพื่อ auto-rollback
                # สร้าง Organization ก่อน
                organization = Organization(
                    name=sanitized_data['organization_name'],
                    contact_email=sanitized_data['contact_email'],
                    phone=sanitized_data.get('phone', ''),
                    address=sanitized_data.get('address', '')
                )
                db.session.add(organization)
                db.session.flush()  # ได้ ID แต่ยังไม่ commit
                
                # สร้าง Admin User
                admin_user = User(
                    organization_id=organization.id,
                    email=sanitized_data['email'],
                    first_name=sanitized_data['first_name'],
                    last_name=sanitized_data['last_name'],
                    role=UserRole.ADMIN
                )
                admin_user.set_password(sanitized_data['password'])
                db.session.add(admin_user)
                db.session.flush()  # ได้ ID แต่ยังไม่ commit
                
                # ตรวจสอบ duplicate อีกครั้ง (ป้องกัน race condition)
                duplicate_check = User.query.filter(
                    User.email == sanitized_data['email'],
                    User.id != admin_user.id
                ).first()
                if duplicate_check:
                    raise ValueError("Email already registered by another request")
                
                # สร้าง TeamUp Calendar (จุดที่อาจจะล้มเหลว)
                from hybrid_teamup_strategy import HybridTeamUpManager
                manager = HybridTeamUpManager()
                
                print(f"Creating TeamUp setup for user: {admin_user.email}")
                setup_result = manager.create_organization_setup(organization)

                if not setup_result['success']:
                    raise Exception(f'Failed to create calendar: {setup_result["error"]}')
                
                # อัปเดต organization ด้วย calendar ID
                organization.teamup_calendar_id = setup_result['primary_calendar_id']
                
                # ถึงจุดนี้แล้วทุกอย่างสำเร็จ - commit transaction
                # (db.session.begin() context manager จะ commit ให้อัตโนมัติ)
            
            print(f"✅ Registration successful for {admin_user.email}")
            print(f"Welcome email would be sent to {admin_user.email}")
            
            return jsonify({
                'success': True,
                'message': 'Registration successful. Please check your email to verify your account.',
                'organization_id': organization.id,
                'redirect_url': url_for('auth.login')
            })
            
        except ValueError as e:
            # Validation หรือ business logic errors
            db.session.rollback()
            return jsonify({'error': str(e), 'field_errors': {'email': str(e)}}), 400
            
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Exception during registration POST: {str(e)}", exc_info=True)
            db.session.rollback()
            
            import sqlalchemy.exc
            if isinstance(e, sqlalchemy.exc.IntegrityError) and "UNIQUE constraint failed" in str(e):
                return jsonify({'error': 'An account with this email already exists.', 'field_errors': {'email': 'Email already registered.'}}), 400
            
            return jsonify({'error': f'Registration failed: {str(e)}'}), 500
    
    # GET request - แสดงหน้า register
    return render_template('auth/register.html', pricing_plans=PRICING_PLANS)

# เพิ่ม rate limiting ที่เข้มงวดขึ้นสำหรับ registration
def enhanced_rate_limit_check(identifier, endpoint='default', max_attempts=5, window_minutes=15):
    """Enhanced rate limiting with endpoint-specific limits"""
    endpoint_limits = {
        'registration': {'max_attempts': 3, 'window_minutes': 60},  # เข้มงวดกว่า
        'login': {'max_attempts': 5, 'window_minutes': 15},
        'default': {'max_attempts': max_attempts, 'window_minutes': window_minutes}
    }
    
    limits = endpoint_limits.get(endpoint, endpoint_limits['default'])
    return rate_limit_check(identifier, limits['max_attempts'], limits['window_minutes'])

# เพิ่ม middleware สำหรับ log requests ที่มาเร็วมาก
@auth_bp.before_request
def log_rapid_requests():
    """Log requests ที่มาเร็วเกินไป"""
    if request.endpoint == 'auth.register' and request.method == 'POST':
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        # ตรวจสอบ request ที่มาเร็วมาก
        cache_key = f"rapid_check:{client_ip}"
        
        try:
            if redis_client:
                last_request = redis_client.get(cache_key)
                if last_request:
                    time_diff = datetime.now(timezone.utc).timestamp() - float(last_request)
                    if time_diff < 2:  # น้อยกว่า 2 วินาที
                        from flask import current_app
                        current_app.logger.warning(f"Rapid registration attempt from {client_ip}: {time_diff:.3f}s between requests")
                
                # บันทึกเวลาปัจจุบัน
                redis_client.setex(cache_key, 10, str(datetime.now(timezone.utc).timestamp()))
                
        except Exception as e:
            print(f"Error in rapid request check: {e}")

# Enhanced Login Route
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            required_fields = ['email', 'password']
            optional_fields = ['otp_code']
            
            sanitized_data, validation_errors = validate_input(data, required_fields, optional_fields)
            
            if validation_errors:
                return jsonify({'error': 'Please provide email and password', 'field_errors': {'email': 'Email is required', 'password': 'Password is required'}}), 400
            
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if not rate_limit_check(client_ip):
                return jsonify({'error': 'Too many login attempts. Please try again later.'}), 429
            
            # **นี่คือจุดที่ 'user' จะถูกกำหนดค่า**
            user = User.query.filter_by(email=sanitized_data['email'], is_active=True).first()
            
            if not user or not user.check_password(sanitized_data['password']):
                record_failed_attempt(client_ip)
                return jsonify({'error': 'Invalid email or password'}), 401
            
            # **ย้ายบล็อกนี้มาไว้ตรงนี้ เพื่อให้แน่ใจว่า 'user' ถูกกำหนดแล้ว**
            if not user.organization:
                # ถ้า user ไม่มี organization (อาจจะข้อมูลไม่สมบูรณ์)
                from flask import current_app
                current_app.logger.error(f"User {user.email} found but has no associated organization.")
                return jsonify({'error': 'Organization data missing for this user. Please contact support.'}), 500

            # Check organization status
            # user.organization.is_subscription_active เป็น hybrid_property (property), ไม่ใช่ method
            if not user.organization.is_subscription_active \
               and user.organization.subscription_status != SubscriptionStatus.TRIAL:
                from flask import current_app
                current_app.logger.warning(
                    f"Login blocked for user {user.email}: Subscription not active ({user.organization.subscription_status.value}) and not in trial."
                )
                return jsonify({'error': 'Organization account is suspended or expired. Please contact administrator.'}), 403
            
            # 2FA Check
            if user.two_factor_enabled:
                otp_code = sanitized_data.get('otp_code', '')
                if not otp_code:
                    return jsonify({'require_2fa': True}), 200
                
                if not verify_2fa_code(user, otp_code):
                    record_failed_attempt(client_ip)
                    return jsonify({'error': 'Invalid OTP code'}), 401
            
            # Login successful
            auth_user = AuthUser(user.id)
            login_user(auth_user, remember=True)
            
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            session['organization_id'] = user.organization_id
            session['teamup_calendar_id'] = user.organization.teamup_calendar_id
            
            return jsonify({
                'success': True,
                'redirect_url': url_for('index'),
                'user': {
                    'name': user.get_full_name(),
                    'role': user.role.value,
                    'organization': user.organization.name
                }
            })
            
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Exception during login POST: {str(e)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Login failed: {str(e)}'}), 500
    
    return render_template('auth/login.html')

# Logout Route
from flask import make_response

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """ทำการ Logout ผู้ใช้ - รองรับทั้ง AJAX และ Normal request"""
    user_id = current_user.get_id()
    
    # ทำการ logout
    logout_user()
    
    # Clear session ทั้งหมด
    session.clear()
    
    # ตรวจสอบว่าเป็น AJAX request หรือไม่
    is_json_request = (
        request.is_json or 
        request.headers.get('Content-Type') == 'application/json' or
        'application/json' in request.headers.get('Accept', '')
    )
    
    if is_json_request:
        # AJAX request - ส่ง JSON
        response = jsonify({
            'success': True,
            'message': 'Logged out successfully.',
            'redirect_url': url_for('auth.login')
        })
    else:
        # Normal request - redirect โดยตรง
        flash('ออกจากระบบสำเร็จ', 'success')
        response = make_response(redirect(url_for('auth.login')))
    
    # เพิ่ม Headers ป้องกันการ Cache
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    # ลบ cookies
    response.set_cookie('session', '', expires=0, path='/', domain=None)
    response.set_cookie('remember_token', '', expires=0, path='/', domain=None)
    
    # Flask-Session cookies
    if 'SESSION_COOKIE_NAME' in current_app.config:
        cookie_name = current_app.config['SESSION_COOKIE_NAME']
        response.set_cookie(cookie_name, '', expires=0, path='/', domain=None)
    
    current_app.logger.info(f'User {user_id} logged out successfully.')
    
    return response

# 2FA Setup
@auth_bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            verification_code = data.get('verification_code')
            
            if not verification_code:
                return jsonify({'error': 'กรุณากรอกรหัสยืนยัน'}), 400
            
            user = current_user.user
            
            # Verify the code
            if verify_2fa_code(user, verification_code):
                user.two_factor_enabled = True
                db.session.commit()
                return jsonify({'success': True, 'message': '2FA ถูกเปิดใช้งานแล้ว'})
            else:
                return jsonify({'error': 'รหัสยืนยันไม่ถูกต้อง'}), 400
                
        except Exception as e:
            return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    
    # Generate 2FA secret
    user = current_user.user
    if not user.two_factor_secret:
        user.two_factor_secret = pyotp.random_base32()
        db.session.commit()
    
    # Generate QR code
    totp_uri = pyotp.totp.TOTP(user.two_factor_secret).provisioning_uri(
        user.email,
        issuer_name=f"NudDee - {user.organization.name}"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    
    return render_template('auth/setup_2fa.html', 
                         qr_code=img_str, 
                         secret=user.two_factor_secret)

# Password Reset Request
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            email = data.get('email')
            
            if not email:
                return jsonify({'error': 'กรุณากรอกอีเมล'}), 400
            
            user = User.query.filter_by(email=email, is_active=True).first()
            
            if user:
                # Generate reset token
                reset_token = user.generate_reset_token()
                db.session.commit()
                
                # Send reset email
                send_password_reset_email(user, reset_token)
            
            # Always return success to prevent email enumeration
            return jsonify({
                'success': True,
                'message': 'หากอีเมลที่ระบุถูกต้อง เราจะส่งลิงก์รีเซ็ตรหัสผ่านไปให้'
            })
            
        except Exception as e:
            return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    
    return render_template('auth/forgot_password.html')

# Password Reset
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token, is_active=True).first()
    
    if not user or not user.is_reset_token_valid():
        flash('ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุแล้ว', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            new_password = data.get('new_password')
            confirm_password = data.get('confirm_password')
            
            # Validate password strength for new password
            is_strong, message = validate_password_strength(new_password)
            if not is_strong:
                return jsonify({'error': message}), 400

            if not new_password or not confirm_password:
                return jsonify({'error': 'กรุณากรอกรหัสผ่านใหม่และยืนยันรหัสผ่าน'}), 400
            
            if new_password != confirm_password:
                return jsonify({'error': 'รหัสผ่านไม่ตรงกัน'}), 400
            
            # Update password
            user.set_password(new_password)
            user.reset_token = None
            user.reset_token_expires = None
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'รีเซ็ตรหัสผ่านสำเร็จ',
                'redirect_url': url_for('auth.login')
            })
            
        except Exception as e:
            return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    
    return render_template('auth/reset_password.html', token=token)

# Helper Functions
def verify_2fa_code(user, code):
    """ตรวจสอบรหัส 2FA"""
    if not user.two_factor_secret:
        return False
    
    totp = pyotp.TOTP(user.two_factor_secret)
    return totp.verify(code, valid_window=1)

def send_welcome_email(user, organization):
    """ส่งอีเมลต้อนรับ"""
    # Implementation depends on your email service
    try:
        # ใช้การตั้งค่าอีเมลจาก config
        mail_server = os.getenv('MAIL_SERVER')
        mail_username = os.getenv('MAIL_USERNAME')
        mail_password = os.getenv('MAIL_PASSWORD')
        
        if not all([mail_server, mail_username, mail_password]):
            print("Email configuration not complete - skipping welcome email")
            return False
        
        # สร้างเนื้อหาอีเมล
        subject = f"ยินดีต้อนรับสู่ NudDee - {organization.name}"
        body = f"""
        สวัสดี {user.get_full_name()},
        
        ยินดีต้อนรับสู่ระบบจัดการนัดหมาย NudDee สำหรับ {organization.name}
        
        บัญชีของคุณได้ถูกสร้างเรียบร้อยแล้ว:
        - อีเมล: {user.email}
        - บทบาท: {user.role.value}
        - ระยะเวลาทดลองใช้: 14 วัน
        
        คุณสามารถเข้าสู่ระบบได้ที่: {os.getenv('APP_URL', 'http://localhost:5000')}/auth/login
        
        ขอบคุณที่เลือกใช้ NudDee
        """
        
        # ส่งอีเมล (สามารถปรับปรุงให้ใช้ Flask-Mail หรือ service อื่นได้)
        print(f"Welcome email would be sent to {user.email}")
        return True
        
    except Exception as e:
        print(f"Error sending welcome email: {e}")
        return False

def send_password_reset_email(user, reset_token):
    """ส่งอีเมลรีเซ็ตรหัสผ่าน"""
    try:
        reset_url = f"{os.getenv('APP_URL', 'http://localhost:5000')}/auth/reset-password/{reset_token}"
        
        subject = "รีเซ็ตรหัสผ่าน - NudDee"
        body = f"""
        สวัสดี {user.get_full_name()},
        
        คุณได้ขอรีเซ็ตรหัสผ่านสำหรับบัญชี NudDee
        
        กรุณาคลิกลิงก์ด้านล่างเพื่อรีเซ็ตรหัสผ่าน:
        {reset_url}
        
        ลิงก์นี้จะหมดอายุภายใน 1 ชั่วโมง
        
        หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยต่ออีเมลนี้
        """
        
        print(f"Password reset email would be sent to {user.email}")
        print(f"Reset URL: {reset_url}")
        return True
        
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False

# Organization Management Routes
@auth_bp.route('/organization/settings')
@login_required
@require_admin # Apply admin decorator
def organization_settings():
    organization = current_user.organization
    return render_template('auth/organization_settings.html', organization=organization)

@auth_bp.route('/organization/users')
@login_required
@require_admin # Apply admin decorator
def manage_users():
    users = User.query.filter_by(organization_id=current_user.user.organization_id).all()
    return render_template('auth/manage_users.html', users=users)

@auth_bp.route('/organization/add-user', methods=['GET', 'POST'])
@login_required
@require_admin # Apply admin decorator
def add_user():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            # Validate input
            required_fields = ['email', 'first_name', 'last_name', 'password']
            optional_fields = ['role']
            sanitized_data, validation_errors = validate_input(data, required_fields, optional_fields)

            if validation_errors:
                return jsonify({'error': 'Validation failed', 'details': validation_errors}), 400

            # Validate email format
            if not validate_email(sanitized_data['email']):
                return jsonify({'error': 'Invalid email format'}), 400
            
            # Validate password strength
            is_strong, message = validate_password_strength(sanitized_data['password'])
            if not is_strong:
                return jsonify({'error': message}), 400

            if User.query.filter_by(email=sanitized_data['email']).first():
                return jsonify({'error': 'อีเมลนี้ถูกใช้งานแล้ว'}), 400
            
            # Check if can add more staff
            if not current_user.organization.can_add_staff():
                return jsonify({'error': 'ไม่สามารถเพิ่มเจ้าหน้าที่ได้ กรุณาอัพเกรดแพ็คเกจ'}), 400
            
            # Determine role
            role = sanitized_data.get('role', 'staff')
            user_role = UserRole.ADMIN if role == 'admin' else UserRole.STAFF

            # Create new user
            new_user = User(
                organization_id=current_user.user.organization_id,
                email=sanitized_data['email'],
                first_name=sanitized_data['first_name'],
                last_name=sanitized_data['last_name'],
                role=user_role
            )
            new_user.set_password(sanitized_data['password'])
            
            db.session.add(new_user)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'เพิ่มผู้ใช้งานสำเร็จ'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    
    return render_template('auth/add_user.html')

@auth_bp.route('/organization/update-settings', methods=['POST'])
@login_required
@require_admin # Apply admin decorator
def update_organization_settings():
    """อัปเดตการตั้งค่าองค์กร"""
    try:
        data = request.get_json() if request.is_json else request.form
        
        organization = current_user.organization
        
        # Validate and sanitize input
        required_fields = ['name', 'contact_email']
        optional_fields = ['phone', 'address']
        sanitized_data, validation_errors = validate_input(data, required_fields, optional_fields)

        if validation_errors:
            return jsonify({'error': 'Validation failed', 'details': validation_errors}), 400
        
        if not validate_email(sanitized_data['contact_email']):
            return jsonify({'error': 'Invalid contact email format'}), 400

        # อัปเดตข้อมูลองค์กร
        organization.name = sanitized_data['name']
        organization.contact_email = sanitized_data['contact_email']
        organization.phone = sanitized_data.get('phone', organization.phone)
        organization.address = sanitized_data.get('address', organization.address)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'อัปเดตข้อมูลองค์กรสำเร็จ'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@auth_bp.route('/toggle-user-status/<user_id>', methods=['POST'])
@login_required
@require_admin # Apply admin decorator
def toggle_user_status(user_id):
    """เปลี่ยนสถานะการใช้งานของผู้ใช้ (เปิด/ปิด)"""
    try:
        user = User.query.filter_by(
            id=user_id,
            organization_id=current_user.user.organization_id
        ).first()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้ที่ระบุ'}), 404
        
        if user.id == current_user.user.id:
            return jsonify({'error': 'ไม่สามารถเปลี่ยนสถานะตัวเองได้'}), 400
        
        # เปลี่ยนสถานะ
        user.is_active = not user.is_active
        
        # บันทึก audit log
        from models import AuditLog
        audit_log = AuditLog(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id,
            action='update',
            resource_type='user',
            resource_id=user_id,
            details={
                'action': 'toggle_status',
                'new_status': 'active' if user.is_active else 'inactive',
                'target_user': user.get_full_name()
            }
        )
        db.session.add(audit_log)
        
        db.session.commit()
        
        status_text = 'เปิดใช้งาน' if user.is_active else 'ระงับ'
        return jsonify({
            'success': True,
            'message': f'{status_text}ผู้ใช้สำเร็จ'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@auth_bp.route('/reset-user-password/<user_id>', methods=['POST'])
@login_required
@require_admin # Apply admin decorator
def reset_user_password(user_id):
    """รีเซ็ตรหัสผ่านของผู้ใช้"""
    try:
        user = User.query.filter_by(
            id=user_id,
            organization_id=current_user.user.organization_id
        ).first()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้ที่ระบุ'}), 404
        
        # สร้างรหัสผ่านใหม่
        import secrets
        import string
        
        # สร้างรหัสผ่านแบบสุ่ม 12 ตัวอักษร
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        new_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # อัปเดตรหัสผ่าน
        user.set_password(new_password)
        
        # บันทึก audit log
        from models import AuditLog
        audit_log = AuditLog(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id,
            action='update',
            resource_type='user',
            resource_id=user_id,
            details={
                'action': 'reset_password',
                'target_user': user.get_full_name()
            }
        )
        db.session.add(audit_log)
        
        db.session.commit()
        
        # ส่งอีเมลรหัสผ่านใหม่ (สามารถปรับปรุงให้ส่งจริงได้)
        send_new_password_email(user, new_password)
        
        return jsonify({
            'success': True,
            'message': 'รีเซ็ตรหัสผ่านสำเร็จ ระบบได้ส่งรหัสผ่านใหม่ทางอีเมลแล้ว'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@auth_bp.route('/delete-user/<user_id>', methods=['DELETE'])
@login_required
@require_admin # Apply admin decorator
def delete_user(user_id):
    """ลบผู้ใช้"""
    try:
        user = User.query.filter_by(
            id=user_id,
            organization_id=current_user.user.organization_id
        ).first()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้ที่ระบุ'}), 404
        
        if user.id == current_user.user.id:
            return jsonify({'error': 'ไม่สามารถลบตัวเองได้'}), 400
        
        # ตรวจสอบว่าเป็น admin คนสุดท้ายหรือไม่
        admin_count = User.query.filter_by(
            organization_id=current_user.user.organization_id,
            role=UserRole.ADMIN,
            is_active=True
        ).count()
        
        if user.role == UserRole.ADMIN and admin_count <= 1:
            return jsonify({'error': 'ไม่สามารถลบผู้ดูแลคนสุดท้ายได้'}), 400
        
        user_name = user.get_full_name()
        
        # บันทึก audit log ก่อนลบ
        from models import AuditLog
        audit_log = AuditLog(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id,
            action='delete',
            resource_type='user',
            resource_id=user_id,
            details={
                'deleted_user': user_name,
                'deleted_email': user.email
            }
        )
        db.session.add(audit_log)
        
        # ลบผู้ใช้
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'ลบผู้ใช้ "{user_name}" สำเร็จ'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

def send_new_password_email(user, new_password):
    """ส่งอีเมลรหัสผ่านใหม่"""
    try:
        subject = "รหัสผ่านใหม่ - NudDee"
        body = f"""
        สวัสดี {user.get_full_name()},
        
        ผู้ดูแลระบบได้รีเซ็ตรหัสผ่านของคุณแล้ว
        
        รหัสผ่านใหม่: {new_password}
        
        กรุณาเข้าสู่ระบบและเปลี่ยนรหัสผ่านใหม่เพื่อความปลอดภัย
        
        ลิงก์เข้าสู่ระบบ: {os.getenv('APP_URL', 'http://localhost:5000')}/auth/login
        """
        
        print(f"New password email would be sent to {user.email}")
        print(f"New password: {new_password}")
        return True
        
    except Exception as e:
        print(f"Error sending new password email: {e}")
        return False
