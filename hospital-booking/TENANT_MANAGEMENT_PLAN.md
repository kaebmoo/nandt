# แผนการพัฒนาระบบจัดการ Tenant (Super Admin System)

ระบบที่จะพัฒนา
Super Admin System - Application แยกต่างหากสำหรับจัดการ tenant ทั้งหมด
✨ Features หลัก
Role-Based Access Control
Super Admin (หลายคน) - จัดการ tenant ทั้งหมด
Hospital Admin - จัดการผู้ให้บริการของตัวเอง
Tenant Management (CRUD)
➕ สร้าง tenant ใหม่ (auto-create schema)
✏️ แก้ไขข้อมูล tenant
🗑️ Soft delete tenant (สามารถ restore ได้)
👁️ ดูรายละเอียดและสถิติ tenant
Tenant Control
🔄 Activate/Deactivate tenant
📅 เปิด/ปิด public booking แยกต่างหาก
📊 Dashboard แสดงภาพรวมทั้งหมด
🏗️ สถาปัตยกรรม

hospital-booking/
├── admin_app/              # ใหม่: Super Admin Application (Port 5001)
│   ├── templates/          # Admin UI
│   ├── auth.py            # Login + @super_admin_required
│   ├── tenant_routes.py   # CRUD operations
│   └── dashboard_routes.py
├── flask_app/             # ปัจจุบัน: Main Application (Port 5000)
├── shared_db/             # แก้ไข: เพิ่ม role, status fields
└── run_admin.py           # ใหม่: Admin app entry point
🗄️ Database Changes
User Model:
เพิ่ม role field (super_admin / hospital_admin)
hospital_id เป็น nullable (super admin ไม่ต้องผูก hospital)
Hospital Model:
เพิ่ม status field (active / inactive / deleted)
เพิ่ม is_public_booking_enabled
เพิ่ม timestamps (created_at, updated_at, deleted_at)
📦 ขั้นตอนการพัฒนา
แผนแบ่งเป็น 6 ขั้นตอนหลัก:
✅ วิเคราะห์และออกแบบระบบ (เสร็จแล้ว)
⏳ เพิ่ม role system ใน User model
⏳ เพิ่ม status fields ใน Hospital model
⏳ สร้าง Super Admin Flask Application
⏳ สร้าง CRUD endpoints และ templates
⏳ แก้ไข middleware ตรวจสอบ tenant status
🚀 การใช้งาน

# 1. Run migration
python migrations/add_tenant_management.py

# 2. สร้าง super admin แรก
python scripts/create_super_admin.py

# 3. Run admin app (แยกจาก main app)
python run_admin.py  # จะรันที่ port 5001

# 4. Access admin panel
http://localhost:5001  # หรือ admin.yourdomain.com
🔐 Security Features
CSRF Protection
Session timeout (2 hours)
Role-based access control
Separate session storage
Rate limiting (optional)
📝 เอกสารครอบคลุม
แผนมีรายละเอียดครบทุกส่วน:
Database migration scripts (พร้อม rollback)
Complete Flask application code
HTML templates (Bootstrap 5)
Deployment guide (systemd + nginx)
Testing checklist
Future enhancements

## สรุปความต้องการ

สร้างระบบจัดการ tenant ที่แยกต่างหากสำหรับ Super Admin โดยมีฟีเจอร์:
- ✅ เพิ่ม tenant ใหม่
- ✅ แก้ไขข้อมูล tenant
- ✅ Soft delete tenant
- ✅ Deactivate/Activate tenant (Block public booking + Hide จากรายการ)
- ✅ Role-based access control (Super Admin vs Hospital Admin)
- ✅ Dashboard สำหรับดูภาพรวม tenant ทั้งหมด

---

## 1. Database Schema Changes

### 1.1 เพิ่ม Role System ใน User Model

**File: `hospital-booking/shared_db/models.py`**

```python
from enum import Enum

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"

class User(PublicBase):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(200))
    name = Column(String(100))
    phone_number = Column(String(20))

    # ใหม่: Role field
    role = Column(Enum(UserRole), nullable=False, default=UserRole.HOSPITAL_ADMIN)

    # hospital_id จะเป็น NULL สำหรับ super_admin
    hospital_id = Column(Integer, ForeignKey('public.hospitals.id'), nullable=True)
    hospital = relationship("Hospital", back_populates="users")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 1.2 เพิ่ม Status Fields ใน Hospital Model

**File: `hospital-booking/shared_db/models.py`**

```python
from enum import Enum

class HospitalStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"  # Deactivated
    DELETED = "deleted"    # Soft deleted

class Hospital(PublicBase):
    __tablename__ = 'hospitals'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    subdomain = Column(String(50), unique=True, nullable=False, index=True)
    schema_name = Column(String(50), unique=True, nullable=False)

    # ใหม่: Status fields
    status = Column(Enum(HospitalStatus), nullable=False, default=HospitalStatus.ACTIVE)
    is_public_booking_enabled = Column(Boolean, default=True)  # สำหรับ control public booking

    # Stripe integration (existing)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))

    # Additional info
    address = Column(Text)
    phone = Column(String(20))
    email = Column(String(120))
    description = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # สำหรับ soft delete

    users = relationship("User", back_populates="hospital", cascade="all, delete-orphan")
```

### 1.3 Database Migration Script

**File: `hospital-booking/migrations/add_tenant_management.py`**

```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def migrate():
    """เพิ่ม role, status fields และ timestamps"""
    db = Session()

    try:
        print("Starting migration...")

        # 1. Add role field to users table
        print("Adding role field to users table...")
        db.execute(text("""
            CREATE TYPE user_role AS ENUM ('super_admin', 'hospital_admin');
        """))
        db.execute(text("""
            ALTER TABLE public.users
            ADD COLUMN role user_role DEFAULT 'hospital_admin' NOT NULL;
        """))

        # 2. Make hospital_id nullable for super admins
        print("Making hospital_id nullable...")
        db.execute(text("""
            ALTER TABLE public.users
            ALTER COLUMN hospital_id DROP NOT NULL;
        """))

        # 3. Add timestamps to users
        print("Adding timestamps to users...")
        db.execute(text("""
            ALTER TABLE public.users
            ADD COLUMN created_at TIMESTAMP DEFAULT NOW(),
            ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
        """))

        # 4. Add status field to hospitals
        print("Adding status field to hospitals...")
        db.execute(text("""
            CREATE TYPE hospital_status AS ENUM ('active', 'inactive', 'deleted');
        """))
        db.execute(text("""
            ALTER TABLE public.hospitals
            ADD COLUMN status hospital_status DEFAULT 'active' NOT NULL,
            ADD COLUMN is_public_booking_enabled BOOLEAN DEFAULT TRUE,
            ADD COLUMN address TEXT,
            ADD COLUMN phone VARCHAR(20),
            ADD COLUMN email VARCHAR(120),
            ADD COLUMN description TEXT,
            ADD COLUMN created_at TIMESTAMP DEFAULT NOW(),
            ADD COLUMN updated_at TIMESTAMP DEFAULT NOW(),
            ADD COLUMN deleted_at TIMESTAMP;
        """))

        # 5. Update existing hospitals to active status
        print("Updating existing hospitals to active status...")
        db.execute(text("""
            UPDATE public.hospitals
            SET status = 'active'
            WHERE status IS NULL;
        """))

        db.commit()
        print("Migration completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Migration failed: {str(e)}")
        raise
    finally:
        db.close()

def rollback():
    """Rollback migration"""
    db = Session()

    try:
        print("Rolling back migration...")

        # Remove fields from hospitals
        db.execute(text("""
            ALTER TABLE public.hospitals
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS is_public_booking_enabled,
            DROP COLUMN IF EXISTS address,
            DROP COLUMN IF EXISTS phone,
            DROP COLUMN IF EXISTS email,
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS created_at,
            DROP COLUMN IF EXISTS updated_at,
            DROP COLUMN IF EXISTS deleted_at;
        """))
        db.execute(text("DROP TYPE IF EXISTS hospital_status;"))

        # Remove fields from users
        db.execute(text("""
            ALTER TABLE public.users
            DROP COLUMN IF EXISTS role,
            DROP COLUMN IF EXISTS created_at,
            DROP COLUMN IF EXISTS updated_at;
        """))
        db.execute(text("DROP TYPE IF EXISTS user_role;"))

        # Make hospital_id NOT NULL again
        db.execute(text("""
            ALTER TABLE public.users
            ALTER COLUMN hospital_id SET NOT NULL;
        """))

        db.commit()
        print("Rollback completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"Rollback failed: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
```

---

## 2. Super Admin Flask Application

### 2.1 โครงสร้าง Directory

```
hospital-booking/
├── admin_app/                      # ใหม่: Super Admin Application
│   ├── __init__.py                # Flask app factory
│   ├── config.py                  # Configuration
│   ├── models.py                  # Reuse shared_db models
│   ├── auth.py                    # Super admin authentication
│   ├── tenant_routes.py           # Tenant CRUD routes
│   ├── dashboard_routes.py        # Dashboard routes
│   ├── forms.py                   # WTForms
│   ├── decorators.py              # @require_super_admin
│   ├── static/                    # CSS, JS
│   │   ├── css/
│   │   │   └── admin.css
│   │   └── js/
│   │       └── admin.js
│   └── templates/                 # HTML templates
│       ├── base.html
│       ├── auth/
│       │   └── login.html
│       ├── dashboard/
│       │   └── index.html
│       └── tenants/
│           ├── list.html
│           ├── create.html
│           ├── edit.html
│           └── view.html
└── run_admin.py                   # ใหม่: Entry point
```

### 2.2 Flask App Factory

**File: `hospital-booking/admin_app/__init__.py`**

```python
from flask import Flask, g
from flask_session import Session
import os
from dotenv import load_dotenv

from shared_db.database import SessionLocal
from admin_app.auth import auth_bp
from admin_app.tenant_routes import tenant_bp
from admin_app.dashboard_routes import dashboard_bp

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), '..', 'admin_session')
    app.config['SESSION_PERMANENT'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = 7200  # 2 hours

    Session(app)

    # Database session management
    @app.before_request
    def setup_db_session():
        if 'db' not in g:
            g.db = SessionLocal()

    @app.teardown_request
    def teardown_db_session(exception=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(tenant_bp, url_prefix='/tenants')
    app.register_blueprint(dashboard_bp, url_prefix='/')

    return app
```

### 2.3 Authentication Blueprint

**File: `hospital-booking/admin_app/auth.py`**

```python
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from shared_db.models import User, UserRole
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """ตรวจสอบว่า login แล้ว"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณา login ก่อนเข้าใช้งาน', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """ตรวจสอบว่าเป็น super admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณา login ก่อนเข้าใช้งาน', 'error')
            return redirect(url_for('auth.login'))

        user = g.db.query(User).filter_by(id=session['user_id']).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
            return redirect(url_for('auth.login'))

        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = g.db.query(User).filter_by(email=email).first()

        if user and user.check_password(password):
            # ตรวจสอบว่าเป็น super admin
            if user.role != UserRole.SUPER_ADMIN:
                flash('คุณไม่มีสิทธิ์เข้าถึงระบบนี้', 'error')
                return render_template('auth/login.html')

            session['user_id'] = user.id
            flash(f'ยินดีต้อนรับ {user.name}', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('อีเมลหรือรหัสผ่านไม่ถูกต้อง', 'error')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('auth.login'))
```

### 2.4 Tenant Management Routes

**File: `hospital-booking/admin_app/tenant_routes.py`**

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from sqlalchemy import text, create_engine
from shared_db.models import Hospital, User, HospitalStatus, TenantBase
from shared_db.database import SessionLocal, engine
from admin_app.auth import super_admin_required
from admin_app.forms import HospitalForm
from datetime import datetime
import os

tenant_bp = Blueprint('tenants', __name__)

@tenant_bp.route('/')
@super_admin_required
def list_tenants():
    """แสดงรายการ tenant ทั้งหมด (ไม่รวม deleted)"""
    tenants = g.db.query(Hospital).filter(
        Hospital.status != HospitalStatus.DELETED
    ).order_by(Hospital.created_at.desc()).all()

    # นับจำนวน users แต่ละ tenant
    tenant_stats = []
    for tenant in tenants:
        user_count = g.db.query(User).filter_by(hospital_id=tenant.id).count()
        tenant_stats.append({
            'hospital': tenant,
            'user_count': user_count
        })

    return render_template('tenants/list.html', tenant_stats=tenant_stats)

@tenant_bp.route('/create', methods=['GET', 'POST'])
@super_admin_required
def create_tenant():
    """สร้าง tenant ใหม่"""
    form = HospitalForm()

    if form.validate_on_submit():
        # ตรวจสอบว่า subdomain ซ้ำหรือไม่
        existing = g.db.query(Hospital).filter_by(subdomain=form.subdomain.data).first()
        if existing:
            flash(f'Subdomain "{form.subdomain.data}" มีอยู่ในระบบแล้ว', 'error')
            return render_template('tenants/create.html', form=form)

        # สร้าง hospital ใหม่
        schema_name = f"tenant_{form.subdomain.data}"
        hospital = Hospital(
            name=form.name.data,
            subdomain=form.subdomain.data,
            schema_name=schema_name,
            address=form.address.data,
            phone=form.phone.data,
            email=form.email.data,
            description=form.description.data,
            status=HospitalStatus.ACTIVE,
            is_public_booking_enabled=True
        )

        try:
            g.db.add(hospital)
            g.db.commit()

            # Event listener จะสร้าง schema อัตโนมัติ
            flash(f'สร้าง tenant "{hospital.name}" สำเร็จ', 'success')
            return redirect(url_for('tenants.view_tenant', tenant_id=hospital.id))

        except Exception as e:
            g.db.rollback()
            flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
            return render_template('tenants/create.html', form=form)

    return render_template('tenants/create.html', form=form)

@tenant_bp.route('/<int:tenant_id>')
@super_admin_required
def view_tenant(tenant_id):
    """ดูรายละเอียด tenant"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        flash('ไม่พบ tenant นี้', 'error')
        return redirect(url_for('tenants.list_tenants'))

    # ดึงรายการ users
    users = g.db.query(User).filter_by(hospital_id=tenant_id).all()

    # ดึงสถิติจาก tenant schema
    stats = get_tenant_stats(hospital.schema_name)

    return render_template('tenants/view.html',
                         hospital=hospital,
                         users=users,
                         stats=stats)

@tenant_bp.route('/<int:tenant_id>/edit', methods=['GET', 'POST'])
@super_admin_required
def edit_tenant(tenant_id):
    """แก้ไขข้อมูล tenant"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        flash('ไม่พบ tenant นี้', 'error')
        return redirect(url_for('tenants.list_tenants'))

    form = HospitalForm(obj=hospital)

    if form.validate_on_submit():
        # ตรวจสอบว่า subdomain ซ้ำหรือไม่ (ยกเว้นตัวเอง)
        existing = g.db.query(Hospital).filter(
            Hospital.subdomain == form.subdomain.data,
            Hospital.id != tenant_id
        ).first()
        if existing:
            flash(f'Subdomain "{form.subdomain.data}" มีอยู่ในระบบแล้ว', 'error')
            return render_template('tenants/edit.html', form=form, hospital=hospital)

        # Update hospital
        hospital.name = form.name.data
        hospital.subdomain = form.subdomain.data
        hospital.address = form.address.data
        hospital.phone = form.phone.data
        hospital.email = form.email.data
        hospital.description = form.description.data
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
    """เปิด/ปิดการใช้งาน tenant (Activate/Deactivate)"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

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
    """เปิด/ปิด public booking"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

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
    """Soft delete tenant"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

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
    """Restore soft-deleted tenant"""
    hospital = g.db.query(Hospital).filter_by(id=tenant_id).first()
    if not hospital:
        return jsonify({'success': False, 'message': 'ไม่พบ tenant นี้'}), 404

    if hospital.status != HospitalStatus.DELETED:
        return jsonify({'success': False, 'message': 'Tenant นี้ไม่ได้ถูกลบ'}), 400

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

def get_tenant_stats(schema_name):
    """ดึงสถิติจาก tenant schema"""
    try:
        with engine.connect() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}", public'))

            # นับจำนวน patients
            result = conn.execute(text('SELECT COUNT(*) FROM patients'))
            patient_count = result.scalar()

            # นับจำนวน providers
            result = conn.execute(text('SELECT COUNT(*) FROM providers'))
            provider_count = result.scalar()

            # นับจำนวน appointments
            result = conn.execute(text('SELECT COUNT(*) FROM appointments'))
            appointment_count = result.scalar()

            # รีเซ็ต search_path
            conn.execute(text('SET search_path TO public'))

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
```

### 2.5 Dashboard Routes

**File: `hospital-booking/admin_app/dashboard_routes.py`**

```python
from flask import Blueprint, render_template, g
from shared_db.models import Hospital, User, HospitalStatus
from admin_app.auth import super_admin_required

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@super_admin_required
def index():
    """Super Admin Dashboard"""

    # สถิติรวม
    total_tenants = g.db.query(Hospital).filter(
        Hospital.status != HospitalStatus.DELETED
    ).count()

    active_tenants = g.db.query(Hospital).filter_by(
        status=HospitalStatus.ACTIVE
    ).count()

    inactive_tenants = g.db.query(Hospital).filter_by(
        status=HospitalStatus.INACTIVE
    ).count()

    total_users = g.db.query(User).filter(
        User.hospital_id.isnot(None)
    ).count()

    # Tenant ล่าสุด
    recent_tenants = g.db.query(Hospital).filter(
        Hospital.status != HospitalStatus.DELETED
    ).order_by(Hospital.created_at.desc()).limit(5).all()

    stats = {
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'inactive_tenants': inactive_tenants,
        'total_users': total_users
    }

    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_tenants=recent_tenants)
```

### 2.6 Forms

**File: `hospital-booking/admin_app/forms.py`**

```python
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp

class HospitalForm(FlaskForm):
    name = StringField('ชื่อผู้ให้บริการ', validators=[
        DataRequired(message='กรุณากรอกชื่อผู้ให้บริการ'),
        Length(max=100)
    ])

    subdomain = StringField('Subdomain', validators=[
        DataRequired(message='กรุณากรอก subdomain'),
        Length(max=50),
        Regexp('^[a-z0-9-]+$', message='subdomain ต้องเป็นตัวอักษรภาษาอังกฤษพิมพ์เล็ก ตัวเลข และ - เท่านั้น')
    ])

    address = TextAreaField('ที่อยู่')
    phone = StringField('เบอร์โทรศัพท์', validators=[Length(max=20)])
    email = StringField('อีเมล', validators=[Email(), Length(max=120)])
    description = TextAreaField('รายละเอียด')

    submit = SubmitField('บันทึก')
```

### 2.7 Entry Point

**File: `hospital-booking/run_admin.py`**

```python
from admin_app import create_app

app = create_app()

if __name__ == '__main__':
    import os

    # Run on different port (5001) to avoid conflict with main Flask app
    port = int(os.environ.get('ADMIN_PORT', 5001))
    app.run(debug=True, port=port, host='0.0.0.0')
```

---

## 3. Template Examples

### 3.1 Base Template

**File: `hospital-booking/admin_app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Super Admin{% endblock %}</title>

    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <!-- Custom CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin.css') }}">

    {% block extra_css %}{% endblock %}
</head>
<body>
    {% if session.get('user_id') %}
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('dashboard.index') }}">
                <i class="fas fa-hospital-user"></i> Super Admin
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('dashboard.index') }}">
                            <i class="fas fa-tachometer-alt"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('tenants.list_tenants') }}">
                            <i class="fas fa-building"></i> Tenants
                        </a>
                    </li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('auth.logout') }}">
                            <i class="fas fa-sign-out-alt"></i> ออกจากระบบ
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>
    {% endif %}

    <main class="container-fluid py-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </main>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <!-- Custom JS -->
    <script src="{{ url_for('static', filename='js/admin.js') }}"></script>

    {% block extra_js %}{% endblock %}
</body>
</html>
```

### 3.2 Tenant List Template

**File: `hospital-booking/admin_app/templates/tenants/list.html`**

```html
{% extends "base.html" %}

{% block title %}Tenant Management{% endblock %}

{% block content %}
<div class="row mb-4">
    <div class="col">
        <h2><i class="fas fa-building"></i> Tenant Management</h2>
    </div>
    <div class="col text-end">
        <a href="{{ url_for('tenants.create_tenant') }}" class="btn btn-primary">
            <i class="fas fa-plus"></i> สร้าง Tenant ใหม่
        </a>
    </div>
</div>

<div class="card">
    <div class="card-body">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>ชื่อผู้ให้บริการ</th>
                    <th>Subdomain</th>
                    <th>Status</th>
                    <th>Public Booking</th>
                    <th>จำนวน Users</th>
                    <th>สร้างเมื่อ</th>
                    <th>จัดการ</th>
                </tr>
            </thead>
            <tbody>
                {% for item in tenant_stats %}
                <tr>
                    <td>{{ item.hospital.id }}</td>
                    <td>{{ item.hospital.name }}</td>
                    <td><code>{{ item.hospital.subdomain }}</code></td>
                    <td>
                        {% if item.hospital.status.value == 'active' %}
                            <span class="badge bg-success">Active</span>
                        {% else %}
                            <span class="badge bg-secondary">Inactive</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if item.hospital.is_public_booking_enabled %}
                            <span class="badge bg-info">เปิด</span>
                        {% else %}
                            <span class="badge bg-warning">ปิด</span>
                        {% endif %}
                    </td>
                    <td>{{ item.user_count }}</td>
                    <td>{{ item.hospital.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <a href="{{ url_for('tenants.view_tenant', tenant_id=item.hospital.id) }}"
                               class="btn btn-info" title="ดูรายละเอียด">
                                <i class="fas fa-eye"></i>
                            </a>
                            <a href="{{ url_for('tenants.edit_tenant', tenant_id=item.hospital.id) }}"
                               class="btn btn-warning" title="แก้ไข">
                                <i class="fas fa-edit"></i>
                            </a>
                            <button class="btn btn-danger"
                                    onclick="deleteTenant({{ item.hospital.id }}, '{{ item.hospital.name }}')"
                                    title="ลบ">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
function deleteTenant(tenantId, tenantName) {
    if (!confirm(`ต้องการลบ tenant "${tenantName}" หรือไม่?\n\n(นี่เป็น soft delete สามารถ restore ได้)`)) {
        return;
    }

    fetch(`/tenants/${tenantId}/delete`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        } else {
            alert('เกิดข้อผิดพลาด: ' + data.message);
        }
    });
}
</script>
{% endblock %}
```

---

## 4. Middleware Changes for Main Flask App

### 4.1 ตรวจสอบ Tenant Status

**File: `hospital-booking/flask_app/app/__init__.py`**

เพิ่มการตรวจสอบ tenant status ใน middleware:

```python
@app.before_request
def setup_tenant_session():
    """Setup tenant-specific database session"""

    # ... existing subdomain extraction code ...

    if subdomain:
        hospital = db.query(Hospital).filter_by(subdomain=subdomain).first()

        if hospital:
            # ตรวจสอบว่า tenant active หรือไม่
            if hospital.status == HospitalStatus.INACTIVE:
                # ให้ admin login ได้ แต่ block public booking
                if request.endpoint and 'public' in request.endpoint:
                    flash('ผู้ให้บริการนี้ปิดให้บริการชั่วคราว', 'error')
                    return render_template('errors/service_unavailable.html'), 503

            elif hospital.status == HospitalStatus.DELETED:
                # Block ทุกอย่าง
                flash('ไม่พบผู้ให้บริการนี้', 'error')
                return render_template('errors/not_found.html'), 404

            # Set search_path
            schema_name = hospital.schema_name
            db.execute(text(f'SET search_path TO "{schema_name}", public'))

            g.tenant = hospital
            g.subdomain = subdomain
            g.db = db
        else:
            # ... existing error handling ...
```

### 4.2 ตรวจสอบ Public Booking

**File: `hospital-booking/flask_app/app/public_booking.py`**

```python
@public_bp.before_request
def check_public_booking_enabled():
    """ตรวจสอบว่า tenant เปิด public booking หรือไม่"""
    if hasattr(g, 'tenant') and g.tenant:
        if not g.tenant.is_public_booking_enabled:
            flash('ผู้ให้บริการนี้ปิดให้บริการจองออนไลน์ชั่วคราว', 'error')
            return render_template('errors/service_unavailable.html'), 503
```

---

## 5. การสร้าง Super Admin แรก

### 5.1 Script สำหรับสร้าง Super Admin

**File: `hospital-booking/scripts/create_super_admin.py`**

```python
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared_db.database import SessionLocal
from shared_db.models import User, UserRole
from getpass import getpass
from dotenv import load_dotenv

load_dotenv()

def create_super_admin():
    """สร้าง super admin user"""
    db = SessionLocal()

    print("=== สร้าง Super Admin ===\n")

    email = input("Email: ")
    name = input("ชื่อ: ")
    phone = input("เบอร์โทร (optional): ") or None
    password = getpass("Password: ")
    confirm_password = getpass("ยืนยัน Password: ")

    if password != confirm_password:
        print("Error: Password ไม่ตรงกัน")
        return

    # ตรวจสอบว่ามี email นี้แล้วหรือไม่
    existing = db.query(User).filter_by(email=email).first()
    if existing:
        print(f"Error: มี email {email} ในระบบแล้ว")
        return

    # สร้าง super admin
    user = User(
        email=email,
        name=name,
        phone_number=phone,
        role=UserRole.SUPER_ADMIN,
        hospital_id=None  # Super admin ไม่ต้องผูกกับ hospital
    )
    user.set_password(password)

    try:
        db.add(user)
        db.commit()
        print(f"\nสร้าง Super Admin สำเร็จ!")
        print(f"Email: {email}")
        print(f"ชื่อ: {name}")
        print(f"Role: {user.role.value}")
    except Exception as e:
        db.rollback()
        print(f"Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_super_admin()
```

---

## 6. ขั้นตอนการ Deploy

### 6.1 Installation Steps

```bash
# 1. Run migration
cd hospital-booking
python migrations/add_tenant_management.py

# 2. Create super admin
python scripts/create_super_admin.py

# 3. Install dependencies (ถ้ามี package ใหม่)
pip install -r requirements.txt

# 4. Run admin app
python run_admin.py
```

### 6.2 Environment Variables

เพิ่มใน `.env`:

```bash
# Super Admin App
ADMIN_PORT=5001
ADMIN_SECRET_KEY=your-secret-key-here
```

### 6.3 Production Deployment

**Option 1: Run as separate service**
```bash
# Main Flask app (port 5000)
gunicorn -w 4 -b 0.0.0.0:5000 "flask_app.app:create_app()"

# Admin app (port 5001)
gunicorn -w 2 -b 0.0.0.0:5001 "admin_app:create_app()"
```

**Option 2: Use systemd services**

Create `/etc/systemd/system/hospital-admin.service`:

```ini
[Unit]
Description=Hospital Booking - Super Admin App
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/hospital-booking
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn -w 2 -b 127.0.0.1:5001 "admin_app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

**Nginx Configuration**

```nginx
# Admin app
server {
    listen 80;
    server_name admin.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Main app (existing)
server {
    listen 80;
    server_name *.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        # ... existing config ...
    }
}
```

---

## 7. Security Considerations

### 7.1 การป้องกัน

1. **CSRF Protection**: ใช้ Flask-WTF CSRF tokens
2. **Session Security**:
   - Separate session folder สำหรับ admin app
   - Short session timeout (2 hours)
3. **Password Policy**: แนะนำให้ใช้ strong password
4. **Audit Log**: (Optional) บันทึก action ของ super admin
5. **IP Whitelist**: (Optional) จำกัด IP ที่เข้าถึง admin app ได้

### 7.2 Rate Limiting

เพิ่ม Flask-Limiter:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    # ... login logic ...
```

---

## 8. Testing Plan

### 8.1 Manual Testing Checklist

- [ ] Login ด้วย super admin account
- [ ] สร้าง tenant ใหม่
- [ ] ตรวจสอบว่า schema ถูกสร้างอัตโนมัติ
- [ ] แก้ไขข้อมูล tenant
- [ ] Deactivate tenant และทดสอบว่า:
  - [ ] Admin ยัง login ได้
  - [ ] Public booking ถูก block
- [ ] Activate tenant กลับ
- [ ] Toggle public booking on/off
- [ ] Soft delete tenant
- [ ] Restore tenant
- [ ] ตรวจสอบ dashboard statistics

### 8.2 Integration Testing

- [ ] ทดสอบว่า tenant status มีผลกับ main Flask app
- [ ] ทดสอบการสร้าง hospital admin ใน deactivated tenant
- [ ] ทดสอบการ book appointment ใน tenant ที่ปิด public booking

---

## 9. Future Enhancements

### Phase 2 Features (Optional)

1. **Audit Log System**
   - บันทึกทุก action ของ super admin
   - ดู history ของ tenant changes

2. **Billing Integration**
   - เชื่อมต่อ Stripe subscription
   - ดู payment history แต่ละ tenant

3. **Analytics Dashboard**
   - สถิติการใช้งานแต่ละ tenant
   - Charts and graphs

4. **Bulk Operations**
   - Activate/Deactivate multiple tenants
   - Export tenant data

5. **Email Notifications**
   - แจ้งเตือน tenant เมื่อ status เปลี่ยน
   - แจ้งเตือน admins

6. **Multi-level Admin Roles**
   - Super Admin (full access)
   - Admin (limited access)
   - Viewer (read-only)

---

## สรุป

แผนนี้ครอบคลุม:

✅ Database schema changes (role system, status fields)
✅ Super Admin Flask application แยกต่างหาก
✅ CRUD operations สำหรับ tenant
✅ Activate/Deactivate functionality
✅ Soft delete with restore
✅ Public booking control
✅ Security measures
✅ Deployment guide

ทั้งหมดนี้ออกแบบมาเพื่อให้:
- แยก admin app ออกจาก main app
- ใช้ role-based access control
- Soft delete เพื่อความปลอดภัย
- สามารถ control public booking ได้แยก
- Deploy ได้ง่าย production-ready

พร้อมเริ่มพัฒนาเมื่อไหร่ก็บอกได้เลยครับ!
