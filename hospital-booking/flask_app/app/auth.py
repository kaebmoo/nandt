# flask_app/app/auth.py - ระบบ Authentication

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify
from werkzeug.security import check_password_hash
from sqlalchemy import text
from shared_db.models import User, Hospital
from shared_db.database import SessionLocal, get_db_session
from .core.tenant_manager import TenantManager
from .utils.url_helper import get_dashboard_url
from .services.otp_service import otp_service
from .services.email_service import queue_otp_email
import re

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

@auth_bp.route('/edit-profile', methods=['POST'])
def edit_profile():
    """แก้ไขข้อมูลโปรไฟล์"""

    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'กรุณาเข้าสู่ระบบ'}), 401

    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if not user:
            return jsonify({'success': False, 'message': 'ไม่พบข้อมูลผู้ใช้'}), 404

        # รับข้อมูลจากฟอร์ม
        new_name = request.form.get('name', '').strip()
        new_email = request.form.get('email', '').strip()
        new_phone = request.form.get('phone_number', '').strip()

        # ตรวจสอบว่ามีการเปลี่ยนแปลงหรือไม่
        email_changed = new_email and new_email != user.email
        phone_changed = new_phone and new_phone != user.phone_number

        # Validate email format if changed
        if email_changed:
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            if not email_pattern.match(new_email):
                return jsonify({'success': False, 'message': 'รูปแบบอีเมลไม่ถูกต้อง'}), 400

            # ตรวจสอบว่าอีเมลซ้ำหรือไม่
            existing_user = db.query(User).filter_by(email=new_email).first()
            if existing_user and existing_user.id != user.id:
                return jsonify({'success': False, 'message': 'อีเมลนี้ถูกใช้งานแล้ว'}), 400

        # ถ้ามีการเปลี่ยน email หรือ phone ต้องส่ง OTP
        if email_changed or phone_changed:
            # เก็บข้อมูลใหม่ไว้ใน session ชั่วคราว
            session['pending_profile_update'] = {
                'name': new_name,
                'email': new_email if email_changed else user.email,
                'phone_number': new_phone if phone_changed else user.phone_number,
                'email_changed': email_changed,
                'phone_changed': phone_changed
            }

            # ส่ง OTP ไปยังอีเมลใหม่ (ถ้ามีการเปลี่ยน) หรืออีเมลเดิม
            target_email = new_email if email_changed else user.email
            otp = otp_service.generate_otp(target_email, expiration=300)

            try:
                queue_otp_email(target_email, otp)
                return jsonify({
                    'success': True,
                    'requires_otp': True,
                    'message': f'ส่งรหัส OTP ไปยัง {target_email} แล้ว',
                    'target_email': target_email
                })
            except Exception as e:
                return jsonify({'success': False, 'message': f'ไม่สามารถส่ง OTP ได้: {str(e)}'}), 500

        # ถ้าแก้แค่ชื่อ ไม่ต้อง OTP
        if new_name:
            user.name = new_name
            db.commit()
            return jsonify({'success': True, 'requires_otp': False, 'message': 'บันทึกข้อมูลเรียบร้อย'})

        return jsonify({'success': False, 'message': 'ไม่มีข้อมูลที่ต้องแก้ไข'}), 400

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    finally:
        db.close()

@auth_bp.route('/verify-profile-otp', methods=['POST'])
def verify_profile_otp():
    """ยืนยัน OTP สำหรับการแก้ไขโปรไฟล์"""

    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'กรุณาเข้าสู่ระบบ'}), 401

    if 'pending_profile_update' not in session:
        return jsonify({'success': False, 'message': 'ไม่พบข้อมูลการแก้ไขที่รอดำเนินการ'}), 400

    otp_input = request.form.get('otp', '').strip()
    if not otp_input:
        return jsonify({'success': False, 'message': 'กรุณากรอกรหัส OTP'}), 400

    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if not user:
            return jsonify({'success': False, 'message': 'ไม่พบข้อมูลผู้ใช้'}), 404

        pending_data = session['pending_profile_update']
        target_email = pending_data['email']

        # ตรวจสอบ OTP
        success, message = otp_service.verify_otp(target_email, otp_input)

        if success:
            # อัพเดทข้อมูล
            user.name = pending_data['name']
            user.email = pending_data['email']
            user.phone_number = pending_data['phone_number']

            db.commit()

            # ลบข้อมูลชั่วคราว
            session.pop('pending_profile_update', None)

            return jsonify({'success': True, 'message': 'บันทึกข้อมูลเรียบร้อย'})
        else:
            return jsonify({'success': False, 'message': message}), 400

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    finally:
        db.close()

@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """เปลี่ยนรหัสผ่าน"""

    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'กรุณาเข้าสู่ระบบ'}), 401

    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if not user:
            return jsonify({'success': False, 'message': 'ไม่พบข้อมูลผู้ใช้'}), 404

        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # ตรวจสอบข้อมูล
        if not current_password or not new_password or not confirm_password:
            return jsonify({'success': False, 'message': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400

        # ตรวจสอบรหัสผ่านปัจจุบัน
        if not user.check_password(current_password):
            return jsonify({'success': False, 'message': 'รหัสผ่านปัจจุบันไม่ถูกต้อง'}), 400

        # ตรวจสอบรหัสผ่านใหม่ตรงกันหรือไม่
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'รหัสผ่านใหม่ไม่ตรงกัน'}), 400

        # ตรวจสอบความแข็งแรงของรหัสผ่าน
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร'}), 400

        # เก็บข้อมูลรหัสผ่านใหม่ไว้ใน session
        session['pending_password_change'] = new_password

        # ส่ง OTP ไปยังอีเมล
        otp = otp_service.generate_otp(user.email, expiration=300)

        try:
            queue_otp_email(user.email, otp)
            return jsonify({
                'success': True,
                'requires_otp': True,
                'message': f'ส่งรหัส OTP ไปยัง {user.email} แล้ว'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'ไม่สามารถส่ง OTP ได้: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
    finally:
        db.close()

@auth_bp.route('/verify-password-otp', methods=['POST'])
def verify_password_otp():
    """ยืนยัน OTP สำหรับการเปลี่ยนรหัสผ่าน"""

    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'กรุณาเข้าสู่ระบบ'}), 401

    if 'pending_password_change' not in session:
        return jsonify({'success': False, 'message': 'ไม่พบข้อมูลการเปลี่ยนรหัสผ่านที่รอดำเนินการ'}), 400

    otp_input = request.form.get('otp', '').strip()
    if not otp_input:
        return jsonify({'success': False, 'message': 'กรุณากรอกรหัส OTP'}), 400

    db = get_db_session()
    try:
        user = db.query(User).filter_by(id=session['user_id']).first()
        if not user:
            return jsonify({'success': False, 'message': 'ไม่พบข้อมูลผู้ใช้'}), 404

        # ตรวจสอบ OTP
        success, message = otp_service.verify_otp(user.email, otp_input)

        if success:
            # เปลี่ยนรหัสผ่าน
            new_password = session['pending_password_change']
            user.set_password(new_password)

            db.commit()

            # ลบข้อมูลชั่วคราว
            session.pop('pending_password_change', None)

            return jsonify({'success': True, 'message': 'เปลี่ยนรหัสผ่านเรียบร้อย'})
        else:
            return jsonify({'success': False, 'message': message}), 400

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500
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
            
