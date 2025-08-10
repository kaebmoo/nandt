# flask_app/app/__init__.py - เพิ่ม Authentication

import os
from flask import Flask, g, request, redirect, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from celery import Celery, Task

# โหลด .env ก่อนเสมอ
load_dotenv()

# Import models (จะใช้ PublicBase แทน Base)
import sys
sys.path.append('.')
from . import models

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

    # --- โหลด Configuration ---
    # ตั้งค่าหลักๆ สำหรับ Flask และ Celery จาก .env
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "a-dev-secret-key"),
        # เพิ่มการตั้งค่าสำหรับ session
        PERMANENT_SESSION_LIFETIME=3600 * 24 * 7,  # 7 วัน
        SESSION_COOKIE_SECURE=False,  # True สำหรับ HTTPS
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        CELERY=dict(
            broker_url=os.environ.get("REDIS_URL"),
            result_backend=os.environ.get("REDIS_URL"),
            # เพิ่ม task imports ที่นี่ ถ้ามี
            # imports=("app.tasks",)
        ),
    )

    # --- Middleware สำหรับ Multi-Tenancy ---
    @app.before_request
    def setup_tenant_session():
        # ไม่ตรวจสอบ subdomain สำหรับ static files หรือ favicon
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return

        db = SessionLocal()
        hostname = request.host.split(':')[0]
        parts = hostname.split('.')
        subdomain = parts[0] if len(parts) > 2 else None
        
        hospital_schema = None
        if subdomain:
            # FIX: ครอบ SQL string ด้วย text()
            stmt = text("SELECT schema_name FROM public.hospitals WHERE subdomain = :subdomain")
            result = db.execute(stmt, {'subdomain': subdomain}).scalar_one_or_none()
            if result:
                hospital_schema = result

        g.tenant = hospital_schema
        
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

    # --- ลงทะเบียนส่วนต่างๆ ---
    # 1. ลงทะเบียน Routes หลัก
    from . import routes
    app.register_blueprint(routes.bp)
    
    # 2. ลงทะเบียน Authentication Routes
    from . import auth
    app.register_blueprint(auth.auth_bp)

    # 3. เริ่มต้น Celery
    celery_init_app(app)

    return app