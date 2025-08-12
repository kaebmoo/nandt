# flask_app/app/__init__.py - อัปเดตให้รองรับ Blueprint ใหม่

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, g, request, redirect, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from celery import Celery, Task
from flask_wtf.csrf import CSRFProtect

# โหลด .env ก่อนเสมอ
load_dotenv()

# Import models (จะใช้ PublicBase แทน Base)
import sys
sys.path.append('.')
from . import models

log_level = os.environ.get('LOG_LEVEL', 'INFO')

# --- ส่วนกลาง ---
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# สร้างเฉพาะ public tables (ไม่สร้าง tenant tables ใน public)
models.PublicBase.metadata.create_all(bind=engine)

# --- Factory สำหรับสร้าง Celery App ---
def celery_init_app(app: Flask) -> Celery:
    """
    สร้างและตั้งค่า Celery instance ให้ทำงานร่วมกับ Flask app context
    """
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    # เก็บ celery instance ไว้ใน extensions ของ app เพื่อให้เข้าถึงได้จากที่อื่น
    app.extensions["celery"] = celery_app
    return celery_app

# --- Factory สำหรับสร้าง Flask App ---
def create_app() -> Flask:
    """
    สร้างและตั้งค่า Flask Application
    """
    app = Flask(__name__)

    # === Setup Logging ===
    app.logger.setLevel(getattr(logging, log_level))
    if not app.debug and not app.testing:
        # Production logging
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler('logs/hospital-booking.log',
                                          maxBytes=10240000,  # 10MB
                                          backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('Hospital Booking startup')
    else:
        # Development logging
        app.logger.setLevel(logging.DEBUG)

    # --- โหลด Configuration ---
    # ตั้งค่าหลักๆ สำหรับ Flask และ Celery จาก .env
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "a-dev-secret-key"),
        # เพิ่มการตั้งค่าสำหรับ session
        PERMANENT_SESSION_LIFETIME=3600 * 24 * 7,  # 7 วัน
        SESSION_COOKIE_SECURE=False,  # True สำหรับ HTTPS
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        
        # WTF-Forms settings
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=3600,  # 1 hour
        
        CELERY=dict(
            broker_url=os.environ.get("REDIS_URL"),
            result_backend=os.environ.get("REDIS_URL"),
            # เพิ่ม task imports ที่นี่ ถ้ามี
            # imports=("app.tasks",)
        ),
    )

    # Initialize CSRF Protection
    csrf = CSRFProtect()
    csrf.init_app(app)

    # --- Middleware สำหรับ Multi-Tenancy ---
    @app.before_request
    def setup_tenant_session():
        # ไม่ตรวจสอบ subdomain สำหรับ static files หรือ favicon
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return

        db = SessionLocal()
        
        # ตรวจสอบ subdomain จาก URL parameter ก่อน (สำหรับ development)
        subdomain_param = request.args.get('subdomain')
        subdomain = None
        
        if subdomain_param:
            subdomain = subdomain_param
        else:
            # ตรวจสอบจาก hostname (สำหรับ production)
            hostname = request.host.split(':')[0]
            parts = hostname.split('.')
            if len(parts) > 1 and parts[0] not in ['localhost', 'www', 'api']:
                subdomain = parts[0]
        
        hospital_schema = None
        if subdomain:
            # FIX: ครอบ SQL string ด้วย text()
            stmt = text("SELECT schema_name FROM public.hospitals WHERE subdomain = :subdomain")
            result = db.execute(stmt, {'subdomain': subdomain}).scalar_one_or_none()
            if result:
                hospital_schema = result

        g.tenant = hospital_schema
        g.subdomain = subdomain
        
        if hospital_schema:
            # FIX: ใช้ text() กับคำสั่ง SET search_path ด้วยเพื่อความปลอดภัย
            db.execute(text(f'SET search_path TO "{hospital_schema}", public'))
        else:
            db.execute(text('SET search_path TO public'))
            
        g.db = db

    @app.teardown_request
    def teardown_tenant_session(exception):
        db = g.pop('db', None)
        if db is not None:
            try:
                if exception:
                    db.rollback()  # Rollback ถ้ามี error
                db.execute(text('SET search_path TO public'))
            except Exception as e:
                print(f"Error in teardown: {e}")
                # ถ้า transaction abort แล้ว ให้ปิดแล้วเปิดใหม่
                try:
                    db.close()
                    db = SessionLocal()
                    db.execute(text('SET search_path TO public'))
                except:
                    pass
            finally:
                db.close()

    # --- Helper Functions ---
    def get_current_user():
        """ดึงข้อมูลผู้ใช้ปัจจุบัน"""
        from flask import session
        if 'user_id' not in session:
            return None
        
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(id=session['user_id']).first()
            if user:
                user.hospital = db.query(models.Hospital).filter_by(id=user.hospital_id).first()
            return user
        finally:
            db.close()

    def get_tenant_info():
        """ดึงข้อมูล tenant ปัจจุบัน"""
        return getattr(g, 'tenant', None), getattr(g, 'subdomain', None)

    # --- Template Functions ---
    @app.template_global()
    def get_current_user():
        """Template function สำหรับดึงข้อมูลผู้ใช้ปัจจุบัน"""
        from flask import session
        if 'user_id' not in session:
            return None
        
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(id=session['user_id']).first()
            if user:
                user.hospital = db.query(models.Hospital).filter_by(id=user.hospital_id).first()
            return user
        finally:
            db.close()

    @app.template_global()
    def get_tenant_info():
        """Template function สำหรับดึงข้อมูล tenant"""
        return getattr(g, 'tenant', None), getattr(g, 'subdomain', None)

    # --- Template Filters ---
    @app.template_filter('day_name_th')
    def day_name_th_filter(day_number):
        """Filter สำหรับแปลงเลขวันเป็นชื่อวันภาษาไทย"""
        day_names = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์']
        return day_names[day_number] if 0 <= day_number < 7 else ''

    @app.template_filter('day_name_th_short')
    def day_name_th_short_filter(day_number):
        """Filter สำหรับแปลงเลขวันเป็นชื่อวันภาษาไทยแบบสั้น"""
        day_names = ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส']
        return day_names[day_number] if 0 <= day_number < 7 else ''

    @app.template_filter('format_time_range')
    def format_time_range_filter(start_time, end_time):
        """Filter สำหรับ format ช่วงเวลา"""
        return f"{start_time} - {end_time}"

    @app.template_filter('thai_date')
    def thai_date_filter(date):
        """Filter สำหรับแปลงวันที่เป็นรูปแบบ dd/mm/yyyy"""
        if not date:
            return ''
        
        try:
            from datetime import datetime
            
            # ถ้าเป็น string
            if isinstance(date, str):
                # ถ้าเป็น yyyy-mm-dd format
                if '-' in date and len(date.split('-')[0]) == 4:
                    parts = date.split('-')
                    if len(parts) == 3:
                        return f"{parts[2]}/{parts[1]}/{parts[0]}"
                # ถ้าเป็น dd/mm/yyyy อยู่แล้ว
                elif '/' in date:
                    return date
                # พยายาม parse
                else:
                    try:
                        dt = datetime.strptime(date[:10], '%Y-%m-%d')
                        return dt.strftime('%d/%m/%Y')
                    except:
                        return date
            
            # ถ้าเป็น datetime/date object
            elif hasattr(date, 'strftime'):
                return date.strftime('%d/%m/%Y')
            
            return str(date)
        except:
            return str(date)

    @app.template_filter('thai_time')
    def thai_time_filter(time):
        """Filter สำหรับ format เวลา"""
        if not time:
            return ''
        
        try:
            if isinstance(time, str):
                return time[:5]  # HH:MM
            return time.strftime('%H:%M')
        except:
            return str(time)

    # --- Context Processors ---
    @app.context_processor
    def inject_template_vars():
        """Context processor สำหรับส่งตัวแปรทั่วไปไป template"""
        return {
            'day_names_th': ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'],
            'day_names_th_short': ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'],
            'current_year': lambda: datetime.now().year + 543,  # ปี พ.ศ.
        }

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template, request
        if request.is_json:
            return {'error': 'ไม่พบหน้าที่ต้องการ'}, 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template, request
        if request.is_json:
            return {'error': 'เกิดข้อผิดพลาดภายในระบบ'}, 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template, request
        if request.is_json:
            return {'error': 'ไม่มีสิทธิ์เข้าถึง'}, 403
        return render_template('errors/403.html'), 403

    # --- ลงทะเบียนส่วนต่างๆ ---
    # 1. ลงทะเบียน Routes หลัก
    from . import routes
    app.register_blueprint(routes.bp)
    
    # 2. ลงทะเบียน Authentication Routes
    from . import auth
    app.register_blueprint(auth.auth_bp)

    # 3. ลงทะเบียน Availability Routes (ใหม่)
    from .availability_routes import availability_bp
    app.register_blueprint(availability_bp)

    # 4. ลงทะเบียน Public Booking Routes (เพิ่มบรรทัดนี้!)
    from .public_booking import public_bp
    app.register_blueprint(public_bp)

    # Exempt the specific view from CSRF protection
    # csrf.exempt('booking.get_availability')

    # 5. เริ่มต้น Celery
    celery_init_app(app)

    return app

# สำหรับ backward compatibility
from .routes import get_current_user, get_tenant_info