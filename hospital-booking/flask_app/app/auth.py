# flask_app/app/auth.py - ระบบ Authentication

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import check_password_hash
from sqlalchemy import text
from shared_db.models import User, Hospital
from shared_db.database import SessionLocal, get_db_session 
from .core.tenant_manager import TenantManager
from .utils.url_helper import get_dashboard_url

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """หน้า Login"""
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('กรุณากรอกอีเมลและรหัสผ่าน', 'error')
            return render_template('auth/login.html')
        
        db = get_db_session()
        try:
            # หาผู้ใช้จากอีเมล
            user = db.query(User).filter_by(email=email).first()
            
            if user and user.check_password(password):
                # Login สำเร็จ
                session['user_id'] = user.id
                session['hospital_id'] = user.hospital_id
                
                # หา hospital ของผู้ใช้
                hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
                
                if hospital:
                    # Redirect ไปยัง dashboard ของโรงพยาบาล
                    dashboard_url = get_dashboard_url(hospital.subdomain)
                    return redirect(dashboard_url)
                else:
                    flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
            else:
                flash('อีเมลหรือรหัสผ่านไม่ถูกต้อง', 'error')
                
        except Exception as e:
            flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
        finally:
            db.close()
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    """ออกจากระบบ"""
    session.clear()
    flash('ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile')
def profile():
    """หน้าโปรไฟล์ผู้ใช้"""
    
    if 'user_id' not in session:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
        
        return render_template('auth/profile.html', user=user, hospital=hospital)
    finally:
        db.close()

# Middleware สำหรับตรวจสอบการ login
def login_required(f):
    """Decorator สำหรับ routes ที่ต้อง login"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณาเข้าสู่ระบบ', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function สำหรับตรวจสอบสิทธิ์เข้าถึง tenant
# แก้ไข check_tenant_access ให้ใช้ TenantManager
def check_tenant_access(subdomain):
    """ตรวจสอบว่าผู้ใช้มีสิทธิ์เข้าถึง tenant นี้หรือไม่"""
    return TenantManager.validate_tenant_access(subdomain)

def get_current_user():
    """ดึงข้อมูลผู้ใช้ปัจจุบัน (Centralized Function)"""
    if 'user_id' not in session:
        return None
    
    # ใช้ g.db ถ้ามีอยู่แล้ว เพื่อประสิทธิภาพ
    db = g.get('db')
    close_db = False
    if db is None:
        db = get_db_session()
        close_db = True
        
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if user:
            user.hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
        return user
    finally:
        if close_db:
            db.close()
            
'''
def check_tenant_access(subdomain):
    """ตรวจสอบว่าผู้ใช้มีสิทธิ์เข้าถึง tenant นี้หรือไม่"""
    
    if 'user_id' not in session:
        return False
    
    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if not user:
            return False
            
        hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
        if not hospital:
            return False
            
        return hospital.subdomain == subdomain
    finally:
        db.close()
'''