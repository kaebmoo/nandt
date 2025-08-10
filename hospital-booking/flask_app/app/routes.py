# flask_app/app/routes.py - ปรับปรุงให้รองรับ Authentication

from datetime import datetime
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
    db = None
    appointments = []
    
    try:
        # ใช้ g.db ที่ setup ไว้ใน middleware หรือสร้างใหม่
        if hasattr(g, 'db') and g.db:
            db = g.db
        else:
            # สร้าง db session ใหม่ถ้าไม่มี
            from . import SessionLocal
            db = SessionLocal()
            g.db = db
        
        # ตั้งค่า search_path สำหรับ tenant นี้
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # ตรวจสอบว่า table appointments มีอยู่และมี columns ที่จำเป็น
        try:
            # ตรวจสอบ table structure ก่อน
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'appointments' 
                AND table_schema = :schema_name
            """), {'schema_name': tenant_schema}).fetchall()
            
            existing_columns = [row[0] for row in result]
            
            if not existing_columns:
                # ไม่มี table appointments
                flash('ระบบกำลังตั้งค่าฐานข้อมูล กรุณารอสักครู่', 'info')
                appointments = []
            elif 'provider_id' not in existing_columns:
                # table เก่า ยังไม่ได้ migrate
                flash('ระบบกำลังอัปเดต กรุณารอสักครู่หรือติดต่อผู้ดูแลระบบ', 'warning')
                # ดึงข้อมูลแบบเก่า (เฉพาะ columns ที่มี)
                old_appointments = db.execute(text("""
                    SELECT id, patient_id, start_time, end_time, notes, created_at
                    FROM appointments 
                    ORDER BY start_time ASC
                """)).fetchall()
                
                # แปลงเป็น format ที่ template เข้าใจได้
                appointments = []
                for apt in old_appointments:
                    appointments.append({
                        'id': apt[0],
                        'patient_id': apt[1],
                        'start_time': apt[2],
                        'end_time': apt[3],
                        'notes': apt[4],
                        'created_at': apt[5],
                        'patient': None,  # ไม่มีข้อมูล patient
                        'provider_id': None,
                        'event_type_id': None,
                        'guest_name': 'ผู้ป่วย (ข้อมูลเก่า)',
                        'status': 'confirmed'
                    })
            else:
                # table ใหม่ ครบถ้วน
                appointments = db.query(Appointment).order_by(Appointment.start_time.asc()).all()
                
        except Exception as db_error:
            print(f"Database query error: {db_error}")
            # ถ้า query ล้มเหลว แต่ connection ยังใช้ได้
            try:
                db.rollback()  # rollback transaction ที่ล้มเหลว
                appointments = []
                flash('เกิดข้อผิดพลาดในการดึงข้อมูล', 'warning')
            except:
                # connection เสีย
                appointments = []
                flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'error')
        
        # ชื่อโรงพยาบาลจาก database
        hospital_display_name = current_user.hospital.name
        
        return render_template('dashboard.html', 
                             hospital_name=hospital_display_name,
                             subdomain=subdomain,
                             current_user=current_user,
                             appointments=appointments)
                             
    except Exception as e:
        # ถ้าเกิด error ระดับ connection หรือ schema
        print(f"Error accessing tenant '{tenant_schema}': {e}")
        
        # ปิด connection ที่เสีย
        if db:
            try:
                db.rollback()
                db.close()
            except:
                pass
            
        # ลบ g.db ที่เสีย
        if hasattr(g, 'db'):
            g.pop('db', None)
        
        # ตรวจสอบว่าเป็น error แบบไหน
        error_msg = str(e).lower()
        if 'does not exist' in error_msg and 'schema' in error_msg:
            flash(f'ไม่พบฐานข้อมูลสำหรับ {subdomain} กรุณาติดต่อผู้ดูแลระบบ', 'error')
        elif 'column' in error_msg and 'does not exist' in error_msg:
            flash('ระบบกำลังอัปเดต กรุณาลองใหม่อีกครั้งในอีกสักครู่', 'warning')
        else:
            flash('เกิดข้อผิดพลาดในการเข้าถึงข้อมูล กรุณาลองใหม่อีกครั้ง', 'error')
        
        return redirect(url_for('main.index'))

# เพิ่ม helper function สำหรับตรวจสอบ database health
def check_tenant_database_health(tenant_schema):
    """ตรวจสอบสุขภาพของ database tenant"""
    try:
        from . import SessionLocal
        db = SessionLocal()
        
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # ตรวจสอบ tables ที่จำเป็น
        required_tables = ['patients', 'appointments', 'providers', 'event_types', 'service_types']
        
        for table in required_tables:
            result = db.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = :table_name 
                    AND table_schema = :schema_name
                )
            """), {'table_name': table, 'schema_name': tenant_schema}).scalar()
            
            if not result:
                return False, f"Missing table: {table}"
        
        # ตรวจสอบ columns ใน appointments
        columns = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'appointments' 
            AND table_schema = :schema_name
        """), {'schema_name': tenant_schema}).fetchall()
        
        existing_columns = [row[0] for row in columns]
        required_columns = ['id', 'patient_id', 'provider_id', 'event_type_id', 'start_time', 'end_time']
        
        for col in required_columns:
            if col not in existing_columns:
                return False, f"Missing column in appointments: {col}"
        
        db.close()
        return True, "OK"
        
    except Exception as e:
        return False, str(e)

# เพิ่ม route สำหรับ admin ตรวจสอบระบบ
@bp.route('/admin/check-database')
def admin_check_database():
    """ตรวจสอบสุขภาพของฐานข้อมูล (สำหรับ admin)"""
    
    # ตรวจสอบสิทธิ์ admin
    current_user = get_current_user()
    if not current_user:
        return {"error": "Unauthorized"}, 401
    
    tenant_schema, subdomain = get_tenant_info()
    if not tenant_schema:
        return {"error": "No tenant found"}, 400
    
    health_ok, message = check_tenant_database_health(tenant_schema)
    
    return {
        "tenant": subdomain,
        "schema": tenant_schema,
        "healthy": health_ok,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

@bp.route('/settings/working-hours')
@login_required
def working_hours():
    """หน้าตั้งค่าเวลาทำการ"""
    current_user = get_current_user()
    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    # ใช้ข้อมูลจาก current_user แทน get_tenant_info()
    hospital = current_user.hospital
    if not hospital:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('settings/working_hours.html', 
                         current_user=current_user)

@bp.route('/book/<provider_url>')
@bp.route('/book/<provider_url>/<event_slug>')
def public_booking(provider_url, event_slug=None):
    """หน้าจองสาธารณะ (ไม่ต้อง login)"""
    
    tenant_schema, subdomain = get_tenant_info()
    
    if not tenant_schema:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # ตั้งค่า database session สำหรับ tenant นี้
        db = SessionLocal()
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # ค้นหา provider จาก URL
        provider = db.query(Provider).filter_by(
            public_booking_url=provider_url,
            is_active=True
        ).first()
        
        if not provider:
            flash('ไม่พบข้อมูลแพทย์', 'error')
            return redirect(url_for('main.index'))
        
        # ดึง event types ของ provider นี้
        event_types = db.query(EventType).filter_by(is_active=True).all()
        
        # ถ้าระบุ event_slug ให้เลือกเฉพาะอันนั้น
        selected_event = None
        if event_slug:
            selected_event = db.query(EventType).filter_by(
                slug=event_slug,
                is_active=True
            ).first()
        
        return render_template('public/booking.html',
                             provider=provider,
                             event_types=event_types,
                             selected_event=selected_event,
                             subdomain=subdomain)
                             
    except Exception as e:
        print(f"Error in public booking: {e}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(url_for('main.index'))
    finally:
        db.close()

@bp.route('/booking-success/<booking_reference>')
def booking_success(booking_reference):
    """หน้าแสดงผลการจองสำเร็จ"""
    
    tenant_schema, subdomain = get_tenant_info()
    
    if not tenant_schema:
        return redirect(url_for('main.index'))
    
    try:
        db = SessionLocal()
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(
            booking_reference=booking_reference
        ).first()
        
        if not appointment:
            flash('ไม่พบข้อมูลการจอง', 'error')
            return redirect(url_for('main.index'))
        
        provider = db.query(Provider).filter_by(id=appointment.provider_id).first()
        event_type = db.query(EventType).filter_by(id=appointment.event_type_id).first()
        
        return render_template('public/booking_success.html',
                             appointment=appointment,
                             provider=provider,
                             event_type=event_type)
                             
    except Exception as e:
        print(f"Error in booking success: {e}")
        return redirect(url_for('main.index'))
    finally:
        db.close()

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

