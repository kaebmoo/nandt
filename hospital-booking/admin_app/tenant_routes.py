"""
Tenant management routes for Super Admin application
CRUD operations for hospitals/tenants
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from sqlalchemy import text
from datetime import datetime

from shared_db.models import Hospital, User, HospitalStatus, UserRole, AuditLog
from shared_db.database import engine
from admin_app.auth import super_admin_required
from admin_app.forms import HospitalForm

tenant_bp = Blueprint('tenants', __name__)

@tenant_bp.route('/')
@super_admin_required
def list_tenants():
    """List all tenants"""
    
    show_deleted = request.args.get('show_deleted') == 'true'
    
    if show_deleted:
        tenants = g.db.query(Hospital).filter(
            Hospital.status == HospitalStatus.DELETED
        ).order_by(Hospital.deleted_at.desc()).all()
    else:
        tenants = g.db.query(Hospital).filter(
            Hospital.status != HospitalStatus.DELETED
        ).order_by(Hospital.created_at.desc()).all()

    # Get user count for each tenant
    tenant_stats = []
    for tenant in tenants:
        user_count = g.db.query(User).filter_by(
            hospital_id=tenant.id,
            role=UserRole.HOSPITAL_ADMIN
        ).count()
        tenant_stats.append({
            'hospital': tenant,
            'user_count': user_count
        })

    return render_template('tenants/list.html', tenant_stats=tenant_stats, show_deleted=show_deleted)

@tenant_bp.route('/create', methods=['GET', 'POST'])
@super_admin_required
def create_tenant():
    """Create a new tenant"""

    form = HospitalForm()

    if form.validate_on_submit():
        subdomain = form.subdomain.data.strip().lower()

        # Check if subdomain already exists
        existing = g.db.query(Hospital).filter_by(subdomain=subdomain).first()
        if existing:
            flash(f'Subdomain "{subdomain}" มีอยู่ในระบบแล้ว', 'error')
            return render_template('tenants/create.html', form=form)

        # Create hospital record
        schema_name = f"tenant_{subdomain}"
        hospital = Hospital(
            name=form.name.data.strip(),
            subdomain=subdomain,
            schema_name=schema_name,
            address=form.address.data.strip() if form.address.data else None,
            phone=form.phone.data.strip() if form.phone.data else None,
            email=form.email.data.strip() if form.email.data else None,
            description=form.description.data.strip() if form.description.data else None,
            status=HospitalStatus.ACTIVE,
            is_public_booking_enabled=True
        )

        try:
            g.db.add(hospital)
            g.db.commit()

            # Event listener will automatically create schema and tables
            flash(f'สร้าง tenant "{hospital.name}" สำเร็จ!', 'success')
            return redirect(url_for('tenants.view_tenant', tenant_id=hospital.id))

        except Exception as e:
            g.db.rollback()
            flash(f'เกิดข้อผิดพลาดในการสร้าง tenant: {str(e)}', 'error')
            return render_template('tenants/create.html', form=form)

    return render_template('tenants/create.html', form=form)

@tenant_bp.route('/<int:tenant_id>')
@super_admin_required
def view_tenant(tenant_id):
    """View tenant details"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        flash('ไม่พบ tenant นี้', 'error')
        return redirect(url_for('tenants.list_tenants'))

    # Get users for this tenant
    users = g.db.query(User).filter_by(
        hospital_id=tenant_id,
        role=UserRole.HOSPITAL_ADMIN
    ).all()

    # Get statistics from tenant schema
    stats = get_tenant_stats(hospital.schema_name)

    return render_template(
        'tenants/view.html',
        hospital=hospital,
        users=users,
        stats=stats
    )

@tenant_bp.route('/<int:tenant_id>/edit', methods=['GET', 'POST'])
@super_admin_required
def edit_tenant(tenant_id):
    """Edit tenant information"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        flash('ไม่พบ tenant นี้', 'error')
        return redirect(url_for('tenants.list_tenants'))

    form = HospitalForm(obj=hospital)

    if form.validate_on_submit():
        subdomain = form.subdomain.data.strip().lower()

        # Check if subdomain is taken by another tenant
        existing = g.db.query(Hospital).filter(
            Hospital.subdomain == subdomain,
            Hospital.id != tenant_id
        ).first()
        if existing:
            flash(f'Subdomain "{subdomain}" มีอยู่ในระบบแล้ว', 'error')
            return render_template('tenants/edit.html', form=form, hospital=hospital)

        # Update hospital
        hospital.name = form.name.data.strip()
        hospital.subdomain = subdomain
        hospital.address = form.address.data.strip() if form.address.data else None
        hospital.phone = form.phone.data.strip() if form.phone.data else None
        hospital.email = form.email.data.strip() if form.email.data else None
        hospital.description = form.description.data.strip() if form.description.data else None
        hospital.updated_at = datetime.utcnow()

        try:
            g.db.commit()
            flash(f'อัพเดท tenant "{hospital.name}" สำเร็จ', 'success')
            return redirect(url_for('tenants.view_tenant', tenant_id=tenant_id))
        except Exception as e:
            g.db.rollback()
            flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')

    return render_template('tenants/edit.html', form=form, hospital=hospital)

@tenant_bp.route('/<int:tenant_id>/toggle-status', methods=['POST'])
@super_admin_required
def toggle_tenant_status(tenant_id):
    """Toggle tenant status between active and inactive"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    # Don't allow toggling deleted tenants
    if hospital.status == HospitalStatus.DELETED:
        return jsonify({'success': False, 'message': 'ไม่สามารถเปลี่ยน status ของ tenant ที่ถูกลบแล้ว'}), 400

    # Toggle status
    if hospital.status == HospitalStatus.ACTIVE:
        hospital.status = HospitalStatus.INACTIVE
        hospital.is_public_booking_enabled = False
        message = f'ปิดการใช้งาน tenant "{hospital.name}" แล้ว'
    else:
        hospital.status = HospitalStatus.ACTIVE
        hospital.is_public_booking_enabled = True
        message = f'เปิดการใช้งาน tenant "{hospital.name}" แล้ว'

    hospital.updated_at = datetime.utcnow()

    try:
        g.db.commit()
        return jsonify({
            'success': True,
            'message': message,
            'status': hospital.status.value
        })
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@tenant_bp.route('/<int:tenant_id>/toggle-public-booking', methods=['POST'])
@super_admin_required
def toggle_public_booking(tenant_id):
    """Toggle public booking on/off"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    # Toggle public booking
    hospital.is_public_booking_enabled = not hospital.is_public_booking_enabled
    hospital.updated_at = datetime.utcnow()

    try:
        g.db.commit()
        status = 'เปิด' if hospital.is_public_booking_enabled else 'ปิด'
        return jsonify({
            'success': True,
            'message': f'{status} public booking สำหรับ "{hospital.name}" แล้ว',
            'is_enabled': hospital.is_public_booking_enabled
        })
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@tenant_bp.route('/<int:tenant_id>/delete', methods=['POST'])
@super_admin_required
def delete_tenant(tenant_id):
    """Soft delete a tenant"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    # Soft delete
    hospital.status = HospitalStatus.DELETED
    hospital.deleted_at = datetime.utcnow()
    hospital.is_public_booking_enabled = False
    hospital.updated_at = datetime.utcnow()

    try:
        g.db.commit()
        flash(f'ลบ tenant "{hospital.name}" สำเร็จ (soft delete)', 'success')
        return jsonify({'success': True, 'message': 'ลบ tenant สำเร็จ'})
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@tenant_bp.route('/<int:tenant_id>/restore', methods=['POST'])
@super_admin_required
def restore_tenant(tenant_id):
    """Restore a soft-deleted tenant"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    if hospital.status != HospitalStatus.DELETED:
        return jsonify({'success': False, 'message': 'Tenant นี้ไม่ได้ถูกลบ'}), 400

    # Restore tenant
    hospital.status = HospitalStatus.ACTIVE
    hospital.deleted_at = None
    hospital.is_public_booking_enabled = True
    hospital.updated_at = datetime.utcnow()

    try:
        g.db.commit()
        flash(f'Restore tenant "{hospital.name}" สำเร็จ', 'success')
        return jsonify({'success': True, 'message': 'Restore tenant สำเร็จ'})
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@tenant_bp.route('/<int:tenant_id>/create-admin', methods=['POST'])
@super_admin_required
def create_admin_user(tenant_id):
    """Create a hospital admin user for this tenant"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    # Get data from request
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    phone_number = request.form.get('phone_number', '').strip()

    # Validate required fields
    if not all([name, email, password]):
        return jsonify({'success': False, 'message': 'กรุณากรอกชื่อ, email และ password'}), 400

    # Check if email already exists
    existing_user = g.db.query(User).filter_by(email=email).first()
    if existing_user:
        return jsonify({'success': False, 'message': f'Email {email} มีอยู่ในระบบแล้ว'}), 400

    # Validate password length
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password ต้องมีอย่างน้อย 6 ตัวอักษร'}), 400

    # Create user
    user = User(
        email=email,
        name=name,
        phone_number=phone_number if phone_number else None,
        role=UserRole.HOSPITAL_ADMIN,
        hospital_id=hospital.id
    )
    user.set_password(password)

    try:
        g.db.add(user)
        g.db.commit()
        return jsonify({
            'success': True,
            'message': f'สร้าง admin user "{name}" สำเร็จ'
        })
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@tenant_bp.route('/<int:tenant_id>/reset-password/<int:user_id>', methods=['POST'])
@super_admin_required
def reset_user_password(tenant_id, user_id):
    """Reset password for a hospital admin user"""

    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    # Get user
    user = g.db.query(User).filter_by(
        id=user_id,
        hospital_id=tenant_id,
        role=UserRole.HOSPITAL_ADMIN
    ).first()

    if not user:
        return jsonify({'success': False, 'message': 'ไม่พบ user นี้'}), 404

    # Get new password from request
    new_password = request.form.get('new_password', '').strip()
    if not new_password:
        return jsonify({'success': False, 'message': 'กรุณากรอก password ใหม่'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password ต้องมีอย่างน้อย 6 ตัวอักษร'}), 400

    # Update password
    user.set_password(new_password)
    user.updated_at = datetime.utcnow()

    try:
        g.db.commit()
        return jsonify({
            'success': True,
            'message': f'Reset password สำหรับ "{user.name}" สำเร็จ'
        })
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

def get_tenant_stats(schema_name):
    """
    Get statistics from a tenant's schema
    Returns counts of patients, providers, and appointments
    """
    try:
        with engine.connect() as conn:
            # Set search path to tenant schema
            conn.execute(text(f'SET search_path TO "{schema_name}", public'))
            conn.commit()

            # Count patients
            result = conn.execute(text('SELECT COUNT(*) FROM patients'))
            patient_count = result.scalar() or 0

            # Count providers
            result = conn.execute(text('SELECT COUNT(*) FROM providers'))
            provider_count = result.scalar() or 0

            # Count appointments
            result = conn.execute(text('SELECT COUNT(*) FROM appointments'))
            appointment_count = result.scalar() or 0

            # Reset search path
            conn.execute(text('SET search_path TO public'))
            conn.commit()

            return {
                'patients': patient_count,
                'providers': provider_count,
                'appointments': appointment_count
            }
    except Exception as e:
        print(f"Error getting tenant stats: {e}")
        return {
            'patients': 0,
            'providers': 0,
            'appointments': 0
        }

@tenant_bp.route('/<int:tenant_id>/audit-logs')
@super_admin_required
def view_tenant_audit_logs(tenant_id):
    """View audit logs for a specific tenant"""
    tenant = g.db.query(Hospital).get(tenant_id)
    if not tenant:
        flash('Tenant not found', 'error')
        return redirect(url_for('tenants.list_tenants'))
    
    tenant_schema = tenant.schema_name
    
    # 1. Switch search path to Tenant Schema (+ public for User join)
    # Using text() for safety, though schema_name comes from our DB.
    try:
        g.db.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        
        # 2. Query Audit Logs (ordered by newest first)
        # Limit to 100 for now to avoid overload, can add pagination later
        logs = g.db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
        
    except Exception as e:
        g.db.rollback()
        flash(f'Error accessing tenant logs: {str(e)}', 'error')
        logs = []
    
    return render_template('tenants/audit_logs.html', tenant=tenant, logs=logs)
