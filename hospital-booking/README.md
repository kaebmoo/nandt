# Hospital Booking System

ระบบจองคิวโรงพยาบาลแบบ Multi-Tenant SaaS Platform

## โครงสร้างโปรเจค

```
hospital-booking/
├── flask_app/          # Web Application หลัก (Port 5001)
├── fastapi_app/        # API Service (Port 8000)
├── admin_app/          # Super Admin Panel (Port 5002)
├── shared_db/          # Shared Database Models
├── migrations/         # Database Migration Scripts
├── scripts/            # Utility Scripts
├── nginx/              # Nginx Configuration
└── worker.py           # Redis/RQ Background Worker
```

## Prerequisites

- Python 3.8+
- PostgreSQL
- Redis

## การติดตั้ง

### 1. Clone และสร้าง Virtual Environment

```bash
cd hospital-booking
python -m venv venv
source venv/bin/activate  # Linux/Mac
# หรือ venv\Scripts\activate  # Windows
```

### 2. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 3. ตั้งค่า Environment Variables

สร้างไฟล์ `.env` ใน root directory:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost/nuddee

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=1

# Flask
FLASK_SECRET_KEY=your-secret-key
SECRET_KEY=your-secret-key

# Email (Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
EMAIL_SENDER=your-email@gmail.com

# Stripe Payment
STRIPE_SECRET_KEY=sk_xxx
STRIPE_PUBLISHABLE_KEY=pk_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# FastAPI
FASTAPI_BASE_URL=http://127.0.0.1:8000

# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### 4. สร้าง Database

```bash
# สร้าง database ใน PostgreSQL
createdb nuddee
```

---

## การ Start Services

### Flask App (Web Application หลัก)

```bash
cd flask_app
python run.py
```

- **Port:** 5001
- **URL:** http://localhost:5001
- **หน้าที่:** Dashboard สำหรับโรงพยาบาล, ระบบจองคิว, จัดการ Provider

### FastAPI App (API Service)

```bash
cd fastapi_app
uvicorn app.main:app --reload --port 8000
```

- **Port:** 8000
- **URL:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **หน้าที่:** RESTful API, Hospital Registration, Stripe Webhooks

### Admin App (Super Admin Panel)

```bash
python run_admin.py
```

- **Port:** 5002 (หรือกำหนดผ่าน `ADMIN_PORT`)
- **URL:** http://localhost:5002
- **หน้าที่:** จัดการ Tenants, ดู Audit Logs, Super Admin Authentication

---

## การ Start Workers

### RQ Worker (Redis Queue)

```bash
python worker.py
```

- **หน้าที่:** ประมวลผล Background Jobs จาก Redis Queue

### Celery Worker

```bash
celery -A flask_app.celery_worker worker --loglevel=info
```

- **หน้าที่:** ประมวลผล Async Tasks

### Celery Beat (Scheduler)

```bash
celery -A flask_app.celery_worker beat --loglevel=info
```

- **หน้าที่:** Scheduled Tasks (เช่น sync holidays ประจำปี)

---

## Quick Start - รันทุก Services พร้อมกัน

เปิด Terminal 6 หน้าต่าง:

```bash
# Terminal 1: FastAPI
cd hospital-booking/fastapi_app
uvicorn app.main:app --reload --port 8000

# Terminal 2: Flask App
cd hospital-booking/flask_app
python run.py

# Terminal 3: Admin Panel
cd hospital-booking
python run_admin.py

# Terminal 4: RQ Worker
cd hospital-booking
python worker.py

# Terminal 5: Celery Worker (optional)
cd hospital-booking
celery -A flask_app.celery_worker worker --loglevel=info

# Terminal 6: Celery Beat (optional)
cd hospital-booking
celery -A flask_app.celery_worker beat --loglevel=info
```

---

## Multi-Tenant URL

### Development Mode

```
http://localhost:5001/dashboard?subdomain=humnoi
```

### Production Mode

```
https://humnoi.yourdomain.com/dashboard
```

---

## Database Migrations

```bash
cd migrations
python <migration_script>.py
```

### Migration Scripts ที่มี:
- `add_tenant_management.py` - เพิ่มระบบจัดการ Tenant
- `add_availability_templates.py` - เพิ่มระบบ Availability Template
- `add_provider_availability_structures.py` - เพิ่มโครงสร้าง Provider
- `add_holiday_features.py` - เพิ่มระบบวันหยุด

---

## Utility Scripts

```bash
cd scripts
```

| Script | คำอธิบาย |
|--------|----------|
| `create_super_admin.py` | สร้าง Super Admin |
| `reset_super_admin.py` | Reset รหัสผ่าน Super Admin |
| `debug_appointments.py` | Debug ข้อมูลการนัดหมาย |
| `update_tenant_schemas.py` | อัพเดท Tenant Schemas |

---

## API Endpoints (FastAPI)

| Method | Endpoint | คำอธิบาย |
|--------|----------|----------|
| POST | `/api/register` | ลงทะเบียนโรงพยาบาล |
| GET | `/api/v1/health` | Health Check |
| POST | `/api/webhook` | Stripe Webhooks |

---

## Logs

- **Flask:** `logs/hospital-booking.log`
- **FastAPI:** `fastapi_app/logs/`
- **Sessions:** `flask_session/`

---

## Tech Stack

- **Backend:** Flask, FastAPI
- **Database:** PostgreSQL (Multi-Schema)
- **Cache/Queue:** Redis, RQ, Celery
- **Payment:** Stripe
- **ORM:** SQLAlchemy
