# Hospital Booking System (NudDee — นัดดี)

ระบบจองคิวโรงพยาบาลแบบ Multi-Tenant SaaS Platform

## เอกสาร

| เอกสาร | สำหรับ |
|---|---|
| README.md (ไฟล์นี้) | นักพัฒนา — ติดตั้งและรันระบบ |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | ผู้ดูแลโรงพยาบาล — คู่มือการใช้งานระบบ |
| [DEPLOYMENT.md](DEPLOYMENT.md) | แผนการ deploy ขึ้น production |
| [CLAUDE.md](CLAUDE.md) | สถาปัตยกรรมและแนวทางแก้โค้ด (สำหรับ AI/นักพัฒนา) |

## Quick Start (วิธีที่แนะนำ)

```bash
./start_all.sh            # start ทุก service: FastAPI + Flask + Admin + RQ worker
./start_all.sh --celery   # เพิ่ม Celery worker + beat (sync วันหยุดอัตโนมัติ)
# กด Ctrl+C ครั้งเดียวเพื่อหยุดทุก service
```

Script จะตรวจ PostgreSQL/Redis ให้, เลือก Python ที่ dependency ครบให้อัตโนมัติ,
เขียน log แยกไฟล์ที่ `logs/<service>.log` และแจ้งเตือนถ้า service ใดหยุดทำงานเอง

| Service | URL |
|---|---|
| Flask (เว็บหลัก) | http://localhost:5001/?subdomain=ชื่อโรงพยาบาล |
| หน้าจองสาธารณะ | http://localhost:5001/book/?subdomain=ชื่อโรงพยาบาล |
| FastAPI (API docs) | http://localhost:8000/docs |
| Super Admin | http://localhost:5002 |

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

# Email (ใช้ส่งอีเมลยืนยันการจอง/เลื่อน/ยกเลิกนัด และ OTP)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
EMAIL_SENDER=your-email@gmail.com
MAIL_DEFAULT_SENDER=noreply@nuddee.com

# SMS ผ่าน NT Digital (สำหรับ OTP — ไม่ตั้งค่าก็รันได้ แค่ส่ง SMS ไม่ได้)
NT_SMS_HOST=smsgw.example.com
NT_SMS_API=/service/SMSWebServiceEngine.php
NT_SMS_USER=xxx
NT_SMS_PASS=xxx
NT_SMS_SENDER=xxx
# ส่ง SMS แจ้งเลื่อน/ยกเลิกนัดให้ผู้จองที่ไม่มีอีเมล (default ปิด — ระบบเตือนให้เจ้าหน้าที่โทรแทน)
ENABLE_SMS_NOTIFICATIONS=false

# Stripe Payment
STRIPE_SECRET_KEY=sk_xxx
STRIPE_PUBLISHABLE_KEY=pk_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# FastAPI
FASTAPI_BASE_URL=http://127.0.0.1:8000

# URL/Domain (production เท่านั้น)
# DOMAIN=nuddee.com
# USE_HTTPS=true

# Super Admin Panel
ADMIN_HOST=127.0.0.1
ADMIN_PORT=5002

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

## รันทุก Services พร้อมกัน

ใช้ `./start_all.sh` (ดู Quick Start ด้านบน) — คำสั่งข้างบนทั้งหมดมีไว้กรณีต้องการรันแยกทีละตัวเพื่อ debug

> หมายเหตุ: ถ้ารัน FastAPI เองโดยตรง ต้องตั้ง `PYTHONPATH` ชี้ root ของ repo ก่อน
> (`export PYTHONPATH=$(pwd)` จาก root) ไม่เช่นนั้นจะ import `shared_db` ไม่เจอ —
> start_all.sh จัดการให้อัตโนมัติ

---

## ข้อมูลเริ่มต้นของ Tenant ใหม่ (Auto Seed)

ทุกครั้งที่สร้างโรงพยาบาลใหม่ (ทั้งสมัครผ่าน `/api/register` และสร้างจาก Super Admin Panel)
ระบบเรียก `shared_db/seed.py → seed_tenant_defaults()` สร้างให้อัตโนมัติ:

- ตารางเวลาทำการ จันทร์-ศุกร์ 08:30-16:30
- ประเภทนัด 2 รายการ (นัดหมายทั่วไป 30 นาที, ปรึกษา/ติดตามอาการ 15 นาที)
- เจ้าหน้าที่ 1 คน ผูกกับตารางเวลาพร้อมตารางทำงาน

ทำให้หน้าจองสาธารณะใช้ได้ทันทีโดยไม่ต้องตั้งค่าใดๆ ก่อน (ผู้ใช้แก้ไขทีหลังได้จากหน้าตั้งค่า)
ฟังก์ชันเป็น idempotent — เรียกซ้ำกับ tenant ที่มีข้อมูลแล้วจะไม่สร้างซ้ำ

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
