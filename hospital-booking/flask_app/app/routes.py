# flask_app/app/routes.py - ปรับปรุงให้รองรับ Authentication

import os
from flask import Blueprint, render_template, redirect, url_for, g, request, session, flash
from .models import Appointment, User, Hospital
from .auth import login_required, check_tenant_access
from . import SessionLocal
from sqlalchemy import text

bp = Blueprint('main', __name__)

def get_tenant_info():
    """
    ดึงข้อมูล tenant จากทั้ง subdomain และ query parameter
    แนวทางเดียวใช้ได้ทั้ง dev และ production
    """
    tenant_schema = None
    subdomain = None
    
    # วิธีที่ 1: จาก query parameter (สำหรับ development และ fallback)
    subdomain_param = request.args.get('subdomain') or request.args.get('tenant')
    if subdomain_param:
        subdomain = subdomain_param
        tenant_schema = f"tenant_{subdomain}"
        return tenant_schema, subdomain
    
    # วิธีที่ 2: จาก subdomain ใน URL (สำหรับ production)
    hostname = request.host.split(':')[0]
    parts = hostname.split('.')
    
    # ตรวจสอบ subdomain patterns
    if len(parts) >= 2:
        potential_subdomain = parts[0]
        
        # ไม่ใช่ subdomain หลัก
        if potential_subdomain not in ['localhost', 'www', 'api']:
            subdomain = potential_subdomain
            tenant_schema = f"tenant_{subdomain}"
            return tenant_schema, subdomain
    
    # วิธีที่ 3: จาก g.tenant ที่ set ไว้ใน middleware
    if hasattr(g, 'tenant') and g.tenant:
        return g.tenant, g.tenant.replace('tenant_', '')
    
    return None, None

def get_current_user():
    """ดึงข้อมูลผู้ใช้ปัจจุบัน"""
    if 'user_id' not in session:
        return None
    
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if user:
            user.hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
        return user
    finally:
        db.close()

@bp.route('/')
def index():
    """หน้าแรก - Smart routing with user context"""
    
    # ตรวจสอบว่าผู้ใช้ login อยู่หรือไม่
    current_user = get_current_user()
    
    tenant_schema, subdomain = get_tenant_info()
    
    # ถ้ามี tenant และผู้ใช้ login แล้ว
    if tenant_schema and current_user:
        # ตรวจสอบสิทธิ์เข้าถึง
        if check_tenant_access(subdomain):
            return redirect(url_for('main.dashboard'))
        else:
            flash('คุณไม่มีสิทธิ์เข้าถึงโรงพยาบาลนี้', 'error')
            return redirect(url_for('auth.logout'))
    
    # ถ้ามี tenant แต่ไม่ได้ login
    elif tenant_schema and not current_user:
        flash('กรุณาเข้าสู่ระบบเพื่อเข้าถึง Dashboard', 'info')
        return redirect(url_for('auth.login'))
    
    # ถ้าผู้ใช้ login แล้วแต่ไม่ได้ระบุ tenant
    elif current_user and not tenant_schema:
        # Redirect ไปยัง dashboard ของโรงพยาบาลตัวเอง
        return redirect(f"/dashboard?subdomain={current_user.hospital.subdomain}")
    
    # แสดง landing page สำหรับผู้ใช้ที่ยังไม่ login
    fastapi_url = os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")
    return render_template('landing.html', 
                         fastapi_base_url=fastapi_url,
                         current_user=current_user)

@bp.route('/dashboard')
def dashboard():
    """Dashboard - ต้อง login และมีสิทธิ์เข้าถึง"""
    
    tenant_schema, subdomain = get_tenant_info()
    
    # ตรวจสอบ tenant
    if not tenant_schema:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    # ตรวจสอบ login
    current_user = get_current_user()
    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    # ตรวจสอบสิทธิ์เข้าถึง
    if not check_tenant_access(subdomain):
        flash('คุณไม่มีสิทธิ์เข้าถึงโรงพยาบาลนี้', 'error')
        return redirect(url_for('auth.logout'))
    
    # ตั้งค่า database session สำหรับ tenant นี้
    try:
        # ใช้ g.db ที่ setup ไว้ใน middleware หรือสร้างใหม่
        if hasattr(g, 'db') and g.db:
            db = g.db
            # ตั้งค่า search_path สำหรับ tenant นี้
            db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        else:
            # สร้าง db session ใหม่ถ้าไม่มี
            from . import SessionLocal
            db = SessionLocal()
            db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
            g.db = db
        
        # Query ข้อมูลจาก tenant schema
        appointments = db.query(Appointment).order_by(Appointment.start_time.asc()).all()
        
        # ชื่อโรงพยาบาลจาก database
        hospital_display_name = current_user.hospital.name
        
        return render_template('dashboard.html', 
                             hospital_name=hospital_display_name,
                             subdomain=subdomain,
                             current_user=current_user,
                             appointments=appointments)
                             
    except Exception as e:
        # ถ้าเกิด error (เช่น schema ไม่มี)
        print(f"Error accessing tenant '{tenant_schema}': {e}")
        flash('เกิดข้อผิดพลาดในการเข้าถึงข้อมูล', 'error')
        return redirect(url_for('main.index'))

@bp.route('/health')
def health():
    """Health check endpoint"""
    
    tenant_schema, subdomain = get_tenant_info()
    current_user = get_current_user()
    
    return {
        "status": "ok",
        "tenant": tenant_schema,
        "subdomain": subdomain,
        "user_logged_in": current_user is not None,
        "user_id": current_user.id if current_user else None,
        "hospital": current_user.hospital.name if current_user and current_user.hospital else None,
        "host": request.host,
        "environment": os.environ.get('ENVIRONMENT', 'development')
    }