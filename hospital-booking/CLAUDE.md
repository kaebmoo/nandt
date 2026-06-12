# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

This is a multi-tenanted hospital booking system with a **hybrid architecture**:

- **Flask App** (`flask_app/`): Main web application for hospital admin dashboards and public booking pages
- **FastAPI App** (`fastapi_app/`): API-only service for event types, availability, bookings, and holidays
- **Shared Database** (`shared_db/`): Common database models and connection logic
- **Multi-tenancy**: PostgreSQL schemas - `public` schema for hospitals/users, tenant-specific schemas for booking data

### Key Components

**Database Architecture:**
- Public schema: `Hospital`, `User` models for multi-tenant management  
- Tenant schemas: `AvailabilityTemplate`, `EventType`, `Provider`, `Patient`, `Booking` models
- Each hospital gets its own schema (e.g., `tenant_humnoi`)

**URL Routing:**
- Development: `localhost/dashboard?subdomain=humnoi` 
- Production: `humnoi.yourdomain.com/dashboard`
- Universal URL generation handles both modes automatically

## Development Commands

### Running the Applications

```bash
# วิธีที่แนะนำ: start ทุก service ในคำสั่งเดียว (ตรวจ Postgres/Redis ให้ด้วย)
./start_all.sh            # FastAPI(8000) + Flask(5001) + Admin(5002) + RQ worker
./start_all.sh --celery   # เพิ่ม Celery worker + beat

# หรือรันแยกทีละตัว:
cd flask_app && python run.py                                 # Flask (port 5001)
cd fastapi_app && uvicorn app.main:app --reload --port 8000   # FastAPI — ต้อง export PYTHONPATH=<repo root> ก่อน
python run_admin.py                                           # Super Admin (port 5002)
python worker.py                                              # RQ background worker
```

### Database Operations

```bash
# Run database migrations
cd migrations && python <migration_script>.py

# Debug database connections
cd migrations && python debug_database.py
```

### Configuration

The application uses `.env` file for configuration. Key environment variables:
- `DATABASE_URL`: PostgreSQL connection
- `REDIS_URL`: Redis for background tasks
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`: Payment processing
- `ENVIRONMENT`: "development" or "production" 
- `DOMAIN`: Base domain for URL generation

## Coding Patterns

### Database Sessions
Always use the established session management:
```python
# In Flask routes
from flask import g
db = g.db  # Set up by before_request middleware

# In FastAPI
from shared_db.database import SessionLocal
db = SessionLocal()
```

### Multi-tenant Database Access
```python
# Tenant schema is automatically set by middleware
# Use text() wrapper for all SQL commands:
from sqlalchemy import text
db.execute(text('SET search_path TO "tenant_schema", public'))
```

**กับดัก search_path ที่ต้องระวัง (บทเรียนจากการ debug จริง มิ.ย. 2026):**
1. **ห้าม `db.commit()` ทันทีหลัง SET search_path** — commit คืน connection กลับ pool
   แล้ว query ถัดไปอาจได้ connection อื่นที่ search_path ไม่ใช่ tenant เดิม
   ให้ SET โดยไม่ commit เพื่อให้ SET อยู่ใน transaction เดียวกับ query
   (ดู pattern ที่ถูกต้องใน `fastapi_app/app/event_types.py` get_tenant_session
   และทุก route ใน `fastapi_app/app/booking.py`)
2. **เก็บค่า attribute ของ ORM instance เป็นตัวแปร local ก่อน `db.commit()`**
   ถ้าต้องใช้หลัง commit — หลัง commit instance จะ expire และการเข้าถึง attribute
   จะ trigger refresh query ที่อาจวิ่งไปผิด schema → ObjectDeletedError
3. **ส่งเฉพาะค่า primitive เข้า FastAPI BackgroundTasks** — task ทำงานหลัง DB session ปิดแล้ว
4. **ห้ามใช้ `bind=db.get_bind()` กับ DDL (create_all / table.create)** — get_bind() คืน engine
   ซึ่งหยิบ connection ใหม่จาก pool ที่ search_path เป็น public → ตารางถูกสร้างลง public schema
   ต้องใช้ `bind=db.connection()` (connection เดียวกับที่ SET search_path ไว้) —
   นี่คือต้นเหตุที่เคยมีตาราง tenant หลงใน public 14 ตาราง (ลบหมดแล้ว มิ.ย. 2026
   ด้วย migrations/drop_stray_public_tenant_tables.py — public ต้องมีแค่ hospitals, users)

### Tenant Seeding (ข้อมูลเริ่มต้นของ tenant ใหม่)
```python
# Logic อยู่ที่เดียว: shared_db/seed.py
from shared_db.seed import seed_tenant_defaults
seed_tenant_defaults(db, schema_name)  # idempotent — ข้ามถ้ามี template อยู่แล้ว
# ถูกเรียกจากทั้ง /api/register (fastapi_app/app/main.py: create_tenant_setup)
# และ Super Admin panel (admin_app/tenant_routes.py: create_tenant)
# ถ้าเพิ่มเส้นทางสร้าง Hospital ใหม่ ต้องเรียกฟังก์ชันนี้ด้วยเสมอ

# วันหยุดราชการ: tenant ใหม่ได้วันหยุดปีปัจจุบันจาก BOT API อัตโนมัติ (best-effort)
from fastapi_app.app.holidays import sync_tenant_holidays
sync_tenant_holidays(db, schema_name)  # idempotent ตามวันที่ — ใช้ตัวเดียวกับ
# endpoint /holidays/sync และ Celery job ประจำปี (2 ม.ค.) ต้องมี BOT_TOKEN ใน .env
```

### Email Notifications (FastAPI)
```python
# อีเมลยืนยัน/เลื่อน/ยกเลิก/ขอเลื่อนนัดส่งจริงผ่าน SMTP: fastapi_app/app/email_service.py
# เรียกผ่าน BackgroundTasks ด้วยค่า primitive เท่านั้น
# การส่งล้มเหลวจะ log (📧/❌ ใน stdout) ไม่ throw — อีเมลต้องไม่ทำให้การจองล้มเหลว
# กับดัก: flask_mail แก้ charset registry ระดับ global (utf-8 body → 8bit)
# email_service จึงต้องใช้ Charset ที่บังคับ BASE64 เอง (_utf8_base64_charset)
# มิฉะนั้นอีเมลภาษาไทยที่ส่งจาก RQ worker (ซึ่ง import app.* → flask_mail) จะพัง
```

### การแจ้งผู้รับบริการเมื่อ admin เปลี่ยนนัด (Flask)
```python
# flask_app/app/services/appointment_notifications.py
from .services.appointment_notifications import notify_patient_appointment_change
notice, category = notify_patient_appointment_change('cancelled' หรือ 'rescheduled', ...)
flash(notice, category)
# ลำดับช่องทาง: มีอีเมล → ส่งอีเมลผ่าน RQ / มีแต่เบอร์ → คืนข้อความเตือนให้เจ้าหน้าที่โทร
# / SMS เป็น option: ENABLE_SMS_NOTIFICATIONS=true (default ปิด) + ต้องมี NT_SMS_* ครบ
# ใช้แล้วใน admin_cancel_appointment, admin_reschedule_appointment, request_reschedule
```

### URL Generation
Always use helper functions instead of `url_for` directly:
```python
# In Python routes
from .utils.url_helper import build_url_with_context
return redirect(build_url_with_context('main.dashboard'))

# In templates  
{{ nav_url('main.dashboard') }}  # Not url_for()
```

### API Integration
FastAPI service calls from Flask:
```python
def get_fastapi_url():
    return os.environ.get('FASTAPI_BASE_URL', 'http://127.0.0.1:8000')

# Use for availability, booking, event type operations
```

## File Structure

```
hospital-booking/
├── flask_app/           # Main web application
│   ├── app/
│   │   ├── __init__.py     # Flask app factory with multi-tenancy setup
│   │   ├── routes.py       # Main dashboard routes  
│   │   ├── auth.py         # Authentication
│   │   ├── public_booking.py # Public booking interface
│   │   ├── core/           # Core utilities
│   │   │   ├── tenant_manager.py
│   │   │   └── template_helpers.py
│   │   └── utils/          # Utility functions
│   │       ├── url_helper.py
│   │       └── security.py
│   └── run.py
├── fastapi_app/         # API service
│   └── app/
│       ├── main.py         # FastAPI app with universal URL generation
│       ├── booking.py      # Booking API endpoints
│       ├── availability.py # Availability management
│       ├── event_types.py  # Event type management
│       └── holidays.py     # Holiday management
├── shared_db/           # Database models and connections
│   ├── models.py           # SQLAlchemy models (PublicBase/TenantBase)
│   └── database.py         # Database connection setup
├── migrations/          # Database migration scripts
└── worker.py           # Redis/RQ background worker
```

## Common Tasks

### Adding New Routes
1. For admin features: Add to `flask_app/app/routes.py` or create new blueprint
2. For API features: Add to appropriate FastAPI router
3. Always use `build_url_with_context()` for redirects
4. Test both subdomain and query parameter URL modes

### Database Changes
1. Create migration script in `migrations/` directory
2. Test on both public and tenant schemas
3. Use `text()` wrapper for all raw SQL

### Multi-tenant Features
1. All tenant-specific data uses tenant schemas automatically
2. Check `g.tenant` for current tenant schema
3. Public data (hospitals, users) stays in public schema

### Testing
Test both URL modes:
- `http://localhost/dashboard?subdomain=hospital1`
- `http://hospital1.localhost/dashboard` (requires local DNS setup)

## Known Issues

- URL generation inconsistency (see `subdomain_fixed.md` for details)
- Some template filters are duplicated across files
- Error handling needs improvement in API integration points
- N+1 query issues in dashboard data loading
- Role-based access control มี enum แต่ยังไม่บังคับใช้ใน routes
- ยังไม่มี test suite

แก้ไปแล้ว (มิ.ย. 2026): อีเมลยืนยันการจองส่งจริง (เดิม mock print),
tenant จาก Super Admin ได้ seed ข้อมูลเริ่มต้นเหมือนเส้นทางสมัครเอง,
แก้ SET search_path + commit pattern ใน booking.py และ holidays.py ที่ทำให้ query หลุด schema,
dashboard มี onboarding checklist / empty state แล้ว,
password reset มีแล้ว (/auth/forgot-password + /auth/reset-password —
OTP 6 หลักทางอีเมล อายุ 15 นาที ไม่เปิดเผยว่าอีเมลมีในระบบ มี rate limit;
otp_service เก็บ interval ลง Redis เพื่อรองรับอายุ OTP ที่ไม่ใช่ 300 วินาที),
หน้า /terms + /privacy (PDPA) มีแล้วและลิงก์ consent ทุกจุดชี้ถูกต้อง,
ตาราง tenant ที่หลงใน public schema ถูกลบหมดแล้วทั้ง 14 ตาราง และปิดต้นเหตุ
(get_bind→connection) — public เหลือแค่ hospitals, users,
admin เลื่อน/ยกเลิก/ขอเลื่อนนัด → แจ้งผู้รับบริการอัตโนมัติแล้ว
(อีเมล / เตือนให้โทรเมื่อมีแต่เบอร์ / SMS เป็น option ปิด default),
tenant ใหม่ได้วันหยุดราชการปีปัจจุบันอัตโนมัติทั้งสองเส้นทางการสร้าง

## Dependencies

Main Python packages:
- Flask with Blueprints, Sessions, Mail
- FastAPI with Pydantic models
- SQLAlchemy for database ORM
- Redis/RQ for background tasks
- Stripe for payment processing
- Celery for scheduled tasks (holiday sync)