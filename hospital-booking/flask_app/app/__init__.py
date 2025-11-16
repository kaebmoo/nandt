# flask_app/app/__init__.py - อัปเดตให้รองรับ Blueprint ใหม่

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, g, request, redirect, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from celery import Celery, Task
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from flask_mail import Mail
from datetime import datetime, timedelta 
from celery.schedules import crontab

from .utils.url_helper import build_url_with_context
from shared_db.database import engine, PublicBase, TenantBase, get_db_session
# Import models (จะใช้ PublicBase แทน Base)
from shared_db import models 

from dotenv import load_dotenv
# โหลด .env ก่อนเสมอ

log_level = os.environ.get('LOG_LEVEL', 'INFO')

# --- ส่วนกลาง ---
# DATABASE_URL = os.environ.get("DATABASE_URL")
# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# สร้างเฉพาะ public tables (ไม่สร้าง tenant tables ใน public)
PublicBase.metadata.create_all(bind=engine)

mail = Mail()

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
    # Load environment variables from .env file at the very beginning
    load_dotenv()

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

    # --- ได้ตำแหน่งที่แน่นอนของโปรเจกต์ ---
    # basedir จะได้พาธเต็มของโฟลเดอร์ที่ไฟล์ __init__.py นี้อยู่ (คือ .../flask_app/app/)
    basedir = os.path.abspath(os.path.dirname(__file__))

    # --- โหลด Configuration ---
    # ตั้งค่าหลักๆ สำหรับ Flask และ Celery จาก .env
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "a-dev-secret-key"),

        LOG_LEVEL=os.environ.get('LOG_LEVEL', 'INFO'),
        ENVIRONMENT=os.environ.get('ENVIRONMENT', 'production'),

        # เพิ่มการตั้งค่าสำหรับ session
        SESSION_TYPE='filesystem',
        # สร้าง Absolute Path ไปยังโฟลเดอร์ flask_session ที่อยู่นอก flask_app/
        # จะหมายถึง "จากโฟลเดอร์ app -> ถอยออกมา 2 ขั้น -> แล้วเข้าไปที่ flask_session"
        SESSION_FILE_DIR=os.path.join(basedir, '..', '..', 'flask_session'),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),  # 2 ชั่วโมง
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
            imports=("app.tasks",),
            # ADD the beat schedule
            beat_schedule={
                'sync-holidays-annually': {
                    'task': 'tasks.sync_all_tenant_holidays',
                    # Runs on January 2nd at 3:15 AM
                    'schedule': crontab(minute='15', hour='3', day_of_month='2', month_of_year='1'),
                },
            }
        ),
    )

    # เพิ่ม Mail configuration
    app.config.update(
        MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
        MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
        MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true',
        MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
        MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
        MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@nuddee.com'),

        NT_SMS_HOST = os.environ.get('NT_SMS_HOST'),
        NT_SMS_API = os.environ.get('NT_SMS_API'),
        NT_SMS_USER = os.environ.get('NT_SMS_USER'),
        NT_SMS_PASS = os.environ.get('NT_SMS_PASS'),
        NT_SMS_SENDER = os.environ.get('NT_SMS_SENDER')
    )

    # Initialize CSRF Protection
    csrf = CSRFProtect()
    csrf.init_app(app)
    Session(app)
    mail.init_app(app) 

    # --- Middleware สำหรับ Multi-Tenancy ---
    @app.before_request
    def setup_tenant_session():
        # ไม่ตรวจสอบ subdomain สำหรับ static files หรือ favicon
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return

        db = get_db_session()
        
        # ตรวจสอบ subdomain จาก URL parameter ก่อน (สำหรับ development)
        subdomain_param = request.args.get('subdomain')
        subdomain = None
        g.subdomain_from_host = False
        
        if subdomain_param:
            # subdomain = subdomain_param
            subdomain = subdomain_param.split('?')[0]
        else:
            # ตรวจสอบจาก hostname (สำหรับ production)
            hostname = request.host.split(':')[0]
            parts = hostname.split('.')
            if len(parts) > 1 and parts[0] not in ['localhost', 'www', 'api']:
                subdomain = parts[0]
                g.subdomain_from_host = True
        
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
                # Reset search path ก่อนคืน connection กลับไปที่ pool
                db.execute(text('SET search_path TO public'))
            except Exception as e:
                # ใช้ app.logger จะดีกว่า print()
                app.logger.error(f"Error during session teardown: {e}")
            finally:
                # ปิด session เสมอ
                db.close()
    # --- Template Helpers ---
    from .core.template_helpers import register_template_filters, register_template_context
    register_template_filters(app)
    register_template_context(app)

    # --- Helper Functions ---
    # Register navigation helper

    from .utils.url_helper import get_nav_params
    app.add_template_global(get_nav_params, 'get_nav_params')
    
    # Register universal URL generator
    @app.template_global('url')
    @app.template_global('nav_url')  # alias สำหรับ backward compatibility
    @app.template_global('smart_url_for')  # alias สำหรับ backward compatibility
    def universal_url_generator(endpoint, **kwargs):
        """Universal URL generator ที่จัดการ subdomain อัตโนมัติ"""
        return build_url_with_context(endpoint, **kwargs)


    # --- Template Functions ---
    @app.template_global()
    def smart_url_for(endpoint, **kwargs):
        """Smart URL generator that handles subdomain correctly"""
        from .utils.url_helper import build_url_with_context
        return build_url_with_context(endpoint, **kwargs)


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

    # 3. ลงทะเบียน Availability Routes 
    from .availability_routes import availability_bp
    app.register_blueprint(availability_bp)

    # 4. ลงทะเบียน Public Booking Routes
    from .public_booking import public_bp
    app.register_blueprint(public_bp)

    # 5. ลงทะเบียน Holiday Routes
    from .holiday_routes import holiday_bp
    app.register_blueprint(holiday_bp)

    # 6. ลงทะเบียน Provider Management Routes
    from .provider_routes import provider_bp
    app.register_blueprint(provider_bp)

    # Exempt the specific view from CSRF protection
    # csrf.exempt('booking.get_availability')

    # --- ลงทะเบียน Template Globals จากไฟล์อื่น ---
    # ทำให้ template สามารถเรียกใช้ {{ get_current_user() }} ได้
    app.add_template_global(auth.get_current_user, 'get_current_user')

    # 6. เริ่มต้น Celery
    celery_init_app(app)

    return app
