# flask_app/app/routes.py - ปรับปรุงให้รองรับ Authentication

import os
import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, g, request, session, flash, jsonify
from sqlalchemy import text
# from sqlalchemy.orm import joinedload
import logging
from shared_db.models import (Appointment, User, Hospital, 
                              Provider, EventType, Patient, 
                              ServiceType, AvailabilityTemplate)
from .auth import login_required, check_tenant_access
from .utils.logger import log_route_access 
from .utils.url_helper import get_dashboard_url, build_url_with_context
from shared_db.database import SessionLocal, get_db_session
from .auth import get_current_user
from .core.tenant_manager import with_tenant, TenantManager
from flask import current_app

# สร้าง logger สำหรับ module นี้
logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

def get_fastapi_url():
    """Get FastAPI base URL"""
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")


@bp.route('/')
def index():
    """หน้าแรก - Smart routing with user context"""

    current_app.logger.debug("Index route called")
    
    # ตรวจสอบว่าผู้ใช้ login อยู่หรือไม่
    current_user = get_current_user()
    current_app.logger.debug(f"Current user: {current_user.email if current_user else 'None'}")
    
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    current_app.logger.debug(f"Tenant: {tenant_schema}, Subdomain: {subdomain}")
    
    # ถ้ามี tenant และผู้ใช้ login แล้ว
    if tenant_schema and current_user:
        current_app.logger.debug("Has tenant and user, checking access...")
        # ตรวจสอบสิทธิ์เข้าถึง
        if check_tenant_access(subdomain):
            current_app.logger.info(f"User {current_user.email} accessing dashboard for {subdomain}")
            return redirect(build_url_with_context('main.dashboard'))
        else:
            current_app.logger.warning(f"Access denied for user {current_user.email} to {subdomain}")
            flash('คุณไม่มีสิทธิ์เข้าถึงโรงพยาบาลนี้', 'error')
            return redirect(url_for('auth.logout'))
    
    # ถ้ามี tenant แต่ไม่ได้ login
    elif tenant_schema and not current_user:
        flash('กรุณาเข้าสู่ระบบเพื่อเข้าถึง Dashboard', 'info')
        return redirect(url_for('auth.login'))
    
    # ถ้าผู้ใช้ login แล้วแต่ไม่ได้ระบุ tenant
    elif current_user and not tenant_schema:
        # Redirect ไปยัง dashboard ของโรงพยาบาลตัวเอง
        return redirect(get_dashboard_url(current_user.hospital.subdomain))
    
    # แสดง landing page สำหรับผู้ใช้ที่ยังไม่ login
    fastapi_url = os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")
    return render_template('landing.html', 
                         fastapi_base_url=fastapi_url,
                         current_user=current_user)

@bp.route('/dashboard')
@log_route_access
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def dashboard():
    """Dashboard - ดึงข้อมูลจาก Database โดยตรง (ไม่ผ่าน API)"""
    
    current_app.logger.debug("Dashboard route called")
    
    current_user = get_current_user()
    tenant_schema = g.tenant_schema
    subdomain = g.subdomain
    
    # เพิ่มการ log เพื่อ debug
    current_app.logger.debug(f"Dashboard - Tenant: {tenant_schema}, Subdomain: {subdomain}")

    if not tenant_schema:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    if not check_tenant_access(subdomain):
        flash('คุณไม่มีสิทธิ์เข้าถึงโรงพยาบาลนี้', 'error')
        return redirect(url_for('auth.logout'))
    
    db = None
    appointments = []
    
    try:
        db = get_db_session()
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # Query appointments พร้อม relationships
        appointments = db.query(Appointment)\
             .order_by(Appointment.start_time.asc())\
             .all()
        
        hospital_display_name = current_user.hospital.name
        
        # คำนวณ statistics และแบ่งหมวดหมู่
        today = datetime.now().date()
        now = datetime.now()
        
        # แบ่งนัดหมายตามสถานะ
        upcoming_appointments = []
        past_appointments = []
        canceled_appointments = []
        
        for apt in appointments:
            if apt.status and apt.status.lower() == 'cancelled':
                canceled_appointments.append(apt)
            elif apt.start_time and apt.start_time >= now:
                upcoming_appointments.append(apt)
            elif apt.start_time:
                past_appointments.append(apt)
        
        # เรียงลำดับ
        upcoming_appointments.sort(key=lambda x: x.start_time)
        past_appointments.sort(key=lambda x: x.start_time, reverse=True)
        canceled_appointments.sort(key=lambda x: x.cancelled_at if x.cancelled_at else x.start_time, reverse=True)
        
        today_count = sum(1 for apt in upcoming_appointments 
                         if apt.start_time.date() == today)
        
        return render_template('dashboard.html', 
                             hospital_name=hospital_display_name,
                             subdomain=subdomain,
                             current_user=current_user,
                             appointments=appointments,
                             upcoming_appointments=upcoming_appointments,
                             past_appointments=past_appointments,
                             canceled_appointments=canceled_appointments,
                             today_count=today_count,
                             now=now)
                             
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {str(e)}", exc_info=True)
        
        if db:
            try:
                db.rollback()
                db.close()
            except:
                pass
        
        flash('เกิดข้อผิดพลาดในการเข้าถึงข้อมูล', 'error')
        return redirect(url_for('main.index'))
    
@bp.route('/appointments/<int:appointment_id>')
@login_required
@with_tenant(require_access=True)
def view_appointment(appointment_id):
    """ดูรายละเอียดนัดหมายสำหรับ Admin"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        subdomain = g.subdomain
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # Query appointment พร้อม relationships
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            flash('ไม่พบนัดหมาย', 'error')
            return redirect(build_url_with_context('main.dashboard'))
        
        # Load relationships
        patient = db.query(Patient).filter_by(id=appointment.patient_id).first() if appointment.patient_id else None
        event_type = db.query(EventType).filter_by(id=appointment.event_type_id).first() if appointment.event_type_id else None
        provider = db.query(Provider).filter_by(id=appointment.provider_id).first() if appointment.provider_id else None
        
        # ตรวจสอบว่าสามารถ reschedule/cancel ได้หรือไม่
        can_reschedule = appointment.start_time > datetime.now() + timedelta(hours=4)
        can_cancel = appointment.start_time > datetime.now() + timedelta(hours=2)
        
        current_user = get_current_user()
        hospital_name = current_user.hospital.name if current_user else 'Hospital'
        
        return render_template('appointments/view.html',
                             appointment=appointment,
                             patient=patient,
                             event_type=event_type,
                             provider=provider,
                             can_reschedule=can_reschedule,
                             can_cancel=can_cancel,
                             hospital_name=hospital_name,
                             subdomain=subdomain,
                             current_user=current_user)
                             
    except Exception as e:
        current_app.logger.error(f"Error viewing appointment: {str(e)}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('main.dashboard'))

@bp.route('/appointments/<int:appointment_id>/admin-reschedule', methods=['GET', 'POST'])
@login_required
@with_tenant(require_access=True)
def admin_reschedule_appointment(appointment_id):
    """Admin เลื่อนนัดหมาย (มีสิทธิ์มากกว่า public)"""
    
    db = get_db_session()
    tenant_schema = g.tenant_schema
    subdomain = g.subdomain
    
    try:
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            flash('ไม่พบนัดหมาย', 'error')
            return redirect(build_url_with_context('main.dashboard'))
        
        if request.method == 'POST':
            # Process reschedule
            new_date = request.form.get('new_date')
            new_time = request.form.get('new_time')
            reason = request.form.get('reason', 'เลื่อนโดยเจ้าหน้าที่')
            
            # สร้าง reschedule request ผ่าน FastAPI
            reschedule_data = {
                'booking_reference': appointment.booking_reference,
                'new_date': new_date,
                'new_time': new_time,
                'reason': f"[Admin] {reason}"
            }
            
            response = requests.post(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/reschedule",
                json=reschedule_data
            )
            
            if response.ok:
                result = response.json()
                flash(f'เลื่อนนัดเรียบร้อยแล้ว - รหัสใหม่: {result["new_booking_reference"]}', 'success')
                
                # ส่ง notification ถ้ามี email/phone
                if appointment.guest_email or appointment.guest_phone:
                    # TODO: Send notification
                    pass
                
                return redirect(build_url_with_context('main.dashboard', subdomain=subdomain))
            else:
                error = response.json()
                flash(error.get('detail', 'ไม่สามารถเลื่อนนัดได้'), 'error')
        
        # GET - แสดง form
        event_type = db.query(EventType).filter_by(id=appointment.event_type_id).first()
        
        # ดึง availability สำหรับ calendar
        availability_schedule = {}
        if event_type and event_type.template_id:
            avail_response = requests.get(
                f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/availability/template/{event_type.template_id}/details"
            )
            if avail_response.ok:
                availability_data = avail_response.json()
                availability_schedule = availability_data.get('schedule', {})
        
        current_user = get_current_user()
        hospital_name = current_user.hospital.name
        
        return render_template('appointments/admin_reschedule.html',
                             appointment=appointment,
                             event_type=event_type,
                             availability_schedule=availability_schedule,
                             hospital_name=hospital_name,
                             subdomain=subdomain,
                             current_user=current_user)
                             
    except Exception as e:
        current_app.logger.error(f"Error in admin reschedule: {str(e)}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('main.dashboard'))

@bp.route('/appointments/<int:appointment_id>/edit', methods=['GET', 'POST'])
@login_required
@with_tenant(require_access=True)
def edit_appointment(appointment_id):
    """แก้ไขนัดหมาย - Redirect ไปหน้า admin reschedule"""
    subdomain = g.subdomain
    # Redirect ไปหน้า admin reschedule แทน เพราะเป็น logic เดียวกัน
    return redirect(build_url_with_context('main.admin_reschedule_appointment', 
                          appointment_id=appointment_id))

@bp.route('/appointments/<int:appointment_id>/request-reschedule', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def request_reschedule(appointment_id):
    """Admin ส่งคำขอเลื่อนนัดให้ผู้ป่วย"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            return jsonify({'error': 'ไม่พบนัดหมาย'}), 404
        
        reason = request.json.get('reason', '')
        suggested_dates = request.json.get('suggested_dates', [])
        
        # บันทึก request ใน database
        # TODO: สร้าง table reschedule_requests ถ้ายังไม่มี
        
        # ส่ง notification
        if appointment.guest_email:
            # TODO: Send email with reschedule link
            reschedule_link = f"{request.host_url}book/reschedule/{appointment.booking_reference}?subdomain={g.subdomain}"
            
            # Mock email sending
            current_app.logger.info(f"Sending reschedule request to {appointment.guest_email}")
            current_app.logger.info(f"Link: {reschedule_link}")
            current_app.logger.info(f"Reason: {reason}")
        
        if appointment.guest_phone:
            # TODO: Send SMS
            pass
        
        # Update appointment status
        appointment.status = 'pending_reschedule'
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'ส่งคำขอเลื่อนนัดเรียบร้อยแล้ว'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error requesting reschedule: {str(e)}")
        if db:
            db.rollback()
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500

@bp.route('/appointments/<int:appointment_id>/admin-cancel', methods=['GET', 'POST'])
@login_required
@with_tenant(require_access=True)
def admin_cancel_appointment(appointment_id):
    """Admin ยกเลิกนัดหมาย พร้อมระบุเหตุผล"""
    
    db = get_db_session()
    tenant_schema = g.tenant_schema
    subdomain = g.subdomain
    
    try:
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            flash('ไม่พบนัดหมาย', 'error')
            return redirect(build_url_with_context('main.dashboard', subdomain=subdomain))
        
        if request.method == 'POST':
            reason = request.form.get('reason')
            
            if not reason:
                flash('กรุณาระบุเหตุผลในการยกเลิก', 'error')
                return redirect(request.url)
            
            # อัพเดต appointment
            appointment.status = 'cancelled'
            appointment.cancelled_at = datetime.datetime.now(datetime.timezone.utc)
            appointment.cancelled_by = 'admin'
            appointment.cancellation_reason = f"[Admin] {reason}"
            
            db.commit()
            
            # ส่ง notification
            if appointment.guest_email:
                current_app.logger.info(f"Sending cancellation notice to {appointment.guest_email}")
                current_app.logger.info(f"Reason: {reason}")
            
            if appointment.guest_phone:
                pass
            
            flash('ยกเลิกนัดหมายเรียบร้อยแล้ว', 'success')
            # แก้ไขตรงนี้ - เพิ่ม subdomain parameter
            return redirect(build_url_with_context('main.dashboard'))
        
        # GET - แสดง form
        current_user = get_current_user()
        hospital_name = current_user.hospital.name
        
        return render_template('appointments/admin_cancel.html',
                             appointment=appointment,
                             hospital_name=hospital_name,
                             subdomain=subdomain,
                             current_user=current_user)
                             
    except Exception as e:
        current_app.logger.error(f"Error in admin cancel: {str(e)}")
        flash('เกิดข้อผิดพลาด', 'error')
        # แก้ไขตรงนี้ด้วย
        return redirect(build_url_with_context('main.dashboard'))
    
# ==================== Appointment Management via FastAPI ====================

@bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def cancel_appointment(appointment_id):
    """ยกเลิกนัดหมายผ่าน Database โดยตรง (ไม่ผ่าน API)"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            return jsonify({'error': 'ไม่พบนัดหมาย'}), 404
        
        # อัพเดต status เหมือนกับที่ FastAPI ทำ
        appointment.status = 'cancelled'  # ใช้ 'cancelled' ตาม database
        appointment.cancelled_at = datetime.datetime.now(datetime.timezone.utc)
        appointment.cancelled_by = 'admin'
        
        db.commit()
        
        current_app.logger.info(f"Appointment {appointment_id} cancelled by admin")
        
        return jsonify({'success': True, 'message': 'ยกเลิกนัดหมายเรียบร้อยแล้ว'})
        
    except Exception as e:
        current_app.logger.error(f"Error cancelling appointment: {str(e)}")
        if db:
            db.rollback()
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500

@bp.route('/appointments/<int:appointment_id>/restore', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def restore_appointment(appointment_id):
    """กู้คืนนัดหมายที่ถูกยกเลิก"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        subdomain = g.subdomain
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            flash('ไม่พบนัดหมาย', 'error')
            return redirect(build_url_with_context('main.dashboard'))
        
        # กู้คืน status
        appointment.status = 'confirmed'
        appointment.cancelled_at = None
        appointment.cancelled_by = None
        appointment.cancellation_reason = None
        
        db.commit()
        
        flash('กู้คืนนัดหมายเรียบร้อยแล้ว', 'success')
        return redirect(build_url_with_context('main.dashboard'))
        
    except Exception as e:
        current_app.logger.error(f"Error restoring appointment: {str(e)}")
        if db:
            db.rollback()
        flash('เกิดข้อผิดพลาดในการกู้คืนนัดหมาย', 'error')
        return redirect(build_url_with_context('main.dashboard'))

@bp.route('/appointments/<int:appointment_id>/delete', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def delete_appointment(appointment_id):
    """ลบนัดหมายถาวร"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            return jsonify({'error': 'ไม่พบนัดหมาย'}), 404
        
        db.delete(appointment)
        db.commit()
        
        return jsonify({'success': True, 'message': 'ลบนัดหมายเรียบร้อยแล้ว'})
        
    except Exception as e:
        current_app.logger.error(f"Error deleting appointment: {str(e)}")
        if db:
            db.rollback()
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500

@bp.route('/appointments/create')
@login_required
@with_tenant(require_access=True)
def create_appointment():
    """สร้างนัดหมายใหม่ - แสดง form"""
    try:
        subdomain = g.subdomain
        
        # ดึง event types จาก FastAPI
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/event-types"
        )
        
        if response.ok:
            data = response.json()
            event_types = data.get('event_types', [])
        else:
            event_types = []
            flash('ไม่สามารถโหลดประเภทการนัดได้', 'warning')
        
        current_user = get_current_user()
        hospital_name = current_user.hospital.name if current_user else 'Hospital'
        
        # ดึงข้อมูลอื่นๆ จาก database
        db = get_db_session()
        tenant_schema = g.tenant_schema
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        patients = db.query(Patient).all()
        providers = db.query(Provider).filter_by(is_active=True).all()
        
        return render_template('appointments/create.html',
                             event_types=event_types,
                             patients=patients,
                             providers=providers,
                             hospital_name=hospital_name,
                             subdomain=subdomain,
                             current_user=current_user)
                             
    except Exception as e:
        current_app.logger.error(f"Error in create appointment: {str(e)}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('main.dashboard'))

@bp.route('/appointments/store', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def store_appointment():
    """บันทึกนัดหมายใหม่ - ใช้ FastAPI"""
    try:
        subdomain = g.subdomain
        
        # เตรียมข้อมูลสำหรับ API
        booking_data = {
            'event_type_id': int(request.form.get('event_type_id')),
            'date': request.form.get('date'),
            'time': request.form.get('time'),
            'guest_name': request.form.get('guest_name'),
            'guest_email': request.form.get('guest_email'),
            'guest_phone': request.form.get('guest_phone'),
            'notes': request.form.get('notes', '')
        }
        
        # ถ้ามี provider_id
        if request.form.get('provider_id'):
            booking_data['provider_id'] = int(request.form.get('provider_id'))
        
        # เรียก FastAPI
        response = requests.post(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/create",
            json=booking_data
        )
        
        if response.ok:
            result = response.json()
            flash(f'สร้างนัดหมายเรียบร้อยแล้ว (Ref: {result["booking_reference"]})', 'success')
        else:
            error_data = response.json()
            flash(error_data.get('detail', 'ไม่สามารถสร้างนัดหมายได้'), 'error')
        
        return redirect(build_url_with_context('main.dashboard'))
        
    except Exception as e:
        current_app.logger.error(f"Error storing appointment: {str(e)}")
        flash('เกิดข้อผิดพลาด', 'error')
        return redirect(build_url_with_context('main.dashboard'))
    
# ==================== AJAX Endpoints for Calendar ====================

@bp.route('/appointments/<int:appointment_id>/quick-cancel', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def quick_cancel_appointment(appointment_id):
    """ยกเลิกนัดหมายแบบเร็ว (AJAX)"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        
        if not appointment:
            return jsonify({'error': 'ไม่พบนัดหมาย'}), 404
        
        # Default reason for quick cancel
        reason = request.json.get('reason', 'ยกเลิกโดยเจ้าหน้าที่')
        
        appointment.status = 'cancelled'
        appointment.cancelled_at = datetime.datetime.now(datetime.timezone.utc)
        appointment.cancelled_by = 'admin'
        appointment.cancellation_reason = reason
        
        db.commit()
        
        return jsonify({'success': True, 'message': 'ยกเลิกนัดหมายเรียบร้อยแล้ว'})
        
    except Exception as e:
        current_app.logger.error(f"Error in quick cancel: {str(e)}")
        if db:
            db.rollback()
        return jsonify({'error': 'เกิดข้อผิดพลาด'}), 500

@bp.route('/api/appointments/availability/<int:event_type_id>/<date>')
@login_required
def get_appointment_availability(event_type_id, date):
    """ดึง available slots สำหรับ admin (proxy ไปยัง FastAPI)"""
    try:
        subdomain = g.subdomain
        
        response = requests.get(
            f"{get_fastapi_url()}/api/v1/tenants/{subdomain}/booking/availability/{event_type_id}",
            params={'date': date}
        )
        
        if response.ok:
            return jsonify(response.json())
        else:
            return jsonify({'error': 'Failed to get availability'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# ==================== Quick Actions ====================

@bp.route('/appointments/quick-add', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def quick_add_appointment():
    """เพิ่มนัดหมายแบบเร็ว (Walk-in)"""
    try:
        db = get_db_session()
        tenant_schema = g.tenant_schema
        
        db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # สร้าง patient ใหม่หรือหาที่มีอยู่
        patient_name = request.json.get('name')
        patient_phone = request.json.get('phone')
        
        patient = db.query(Patient).filter_by(phone_number=patient_phone).first()
        if not patient:
            patient = Patient(
                name=patient_name,
                phone_number=patient_phone
            )
            db.add(patient)
            db.flush()
        
        # สร้าง appointment
        from .models import generate_booking_reference
        
        appointment = Appointment(
            patient_id=patient.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=30),
            booking_reference=generate_booking_reference(),
            status='confirmed',
            guest_name=patient_name,
            guest_phone=patient_phone,
            notes='Walk-in'
        )
        
        db.add(appointment)
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'เพิ่มนัดหมายเรียบร้อยแล้ว',
            'booking_reference': appointment.booking_reference
        })
        
    except Exception as e:
        if db:
            db.rollback()
        return jsonify({'error': str(e)}), 500

# เพิ่ม helper function สำหรับตรวจสอบ database health
def check_tenant_database_health(tenant_schema):
    """ตรวจสอบสุขภาพของ database tenant"""
    try:
        # from . import SessionLocal
        db = get_db_session()
        
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
    
    tenant_schema, subdomain = TenantManager.get_tenant_context()
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
    """หน้าตั้งค่าเวลาทำการ (เก่า - redirect ไปใหม่)"""
    return redirect(build_url_with_context('availability.availability_settings'))

# @bp.route('/settings/availability')
# @login_required  
# def availability_settings():
#     """หน้าตั้งค่าเวลาทำการ (Availability) - ถูกย้ายไป availability_routes.py"""
#     # Redirect ไปยัง availability blueprint
#     return redirect(build_url_with_context('availability.availability_settings'))

@bp.route('/settings/event-types')
@login_required
def event_types_settings():
    """หน้าตั้งค่าประเภทการนัดหมาย (Event Types)"""
    current_user = get_current_user()
    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    hospital = current_user.hospital
    if not hospital:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('settings/event-types.html', 
                         current_user=current_user)

@bp.route('/booking/<provider_url>')
@bp.route('/booking/<provider_url>/<event_slug>')
def public_booking(provider_url, event_slug=None):
    """หน้าจองสาธารณะ (ไม่ต้อง login)"""
    
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not tenant_schema:
        flash('ไม่พบข้อมูลโรงพยาบาล', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # ตั้งค่า database session สำหรับ tenant นี้
        db = get_db_session()
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
        current_app.logger.error(f"Error in public booking page for provider '{provider_url}': {e}", exc_info=True)
        flash('เกิดข้อผิดพลาดในการโหลดหน้าจอง', 'error')
        return redirect(url_for('main.index'))

@bp.route('/booking-success/<booking_reference>')
def booking_success(booking_reference):
    """หน้าแสดงผลการจองสำเร็จ"""
    
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not tenant_schema:
        return redirect(url_for('main.index'))
    
    try:
        db = get_db_session()
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
        current_app.logger.error(f"Error in booking success page for ref '{booking_reference}': {e}", exc_info=True)
        flash('เกิดข้อผิดพลาดในการแสดงผลการจอง', 'error')
        return redirect(url_for('main.index'))

@bp.route('/health')
def health():
    """Health check endpoint"""
    
    tenant_schema, subdomain = TenantManager.get_tenant_context()
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

@bp.route('/favicon.ico')
def favicon():
    """Favicon route to prevent 404 errors"""
    # Return a simple 204 No Content response to avoid 404 errors
    from flask import Response
    return Response(status=204)
