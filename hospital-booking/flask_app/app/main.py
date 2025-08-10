# hospital-booking/flask_app/app/main.py

from flask import Flask, g, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from celery import Celery

# --- App and Celery Initialization ---
app = Flask(__name__)
celery = Celery(app.name, broker=os.environ.get('REDIS_URL'))
# ... config อื่นๆ ...

# --- Database Connection ---
engine = create_engine(os.environ.get('DATABASE_URL'))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@app.before_request
def setup_tenant_session():
    """
    Middleware ที่จะทำงานก่อนทุก request เพื่อสลับ Schema
    """
    subdomain = request.host.split('.')[0]
    db = SessionLocal()
    
    # 1. ค้นหา tenant จาก public schema
    hospital = db.execute(f"SELECT schema_name FROM public.hospitals WHERE subdomain = '{subdomain}'").scalar_one_or_none()

    if not hospital:
        # อาจจะ redirect ไปหน้า "not found" หรือหน้าสมัคร
        g.tenant = None
        g.db = db
        return
        
    # 2. ตั้งค่า g (global object ของ request)
    g.tenant = hospital
    
    # 3. สั่งให้ session นี้ใช้ schema ของ tenant นั้น
    db.execute(f'SET search_path TO "{hospital}", public')
    g.db = db


@app.teardown_request
def teardown_tenant_session(exception):
    db = g.pop('db', None)
    if db is not in None:
        # คืน search_path กลับเป็น public
        db.execute('SET search_path TO public')
        db.close()

# --- Routes ---
@app.route('/dashboard')
def dashboard():
    if not g.tenant:
        return "Hospital not found", 404
    
    # ตอนนี้เรา query จาก schema ของ tenant นั้นๆ ได้เลย
    # from .models_tenant import Appointment
    # appointments = g.db.query(Appointment).all()
    
    # return render_template('dashboard.html', appointments=appointments)
    return f"<h1>Welcome to {g.tenant}'s Dashboard</h1>"