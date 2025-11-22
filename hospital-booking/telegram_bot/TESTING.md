# Testing Guide - Telegram Bot

คู่มือการทดสอบ Telegram Bot สำหรับ Hospital Booking System

## 📋 Table of Contents

- [Pre-requisites](#pre-requisites)
- [Health Check](#health-check)
- [Running Tests](#running-tests)
- [Manual Testing](#manual-testing)
- [Troubleshooting](#troubleshooting)

---

## Pre-requisites

### 1. Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install all dependencies including test packages
pip install -r requirements.txt
```

### 2. Start Required Services

**Terminal 1: FastAPI Backend**
```bash
cd ../fastapi_app
uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Redis**
```bash
# Using system Redis
redis-server

# Or using Docker
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 3. Configure Environment

```bash
# Copy and edit .env
cp .env.example .env
nano .env
```

Required variables:
```env
TELEGRAM_BOT_TOKEN=your_token_here
FASTAPI_BASE_URL=http://localhost:8000
DEFAULT_SUBDOMAIN=humnoi
REDIS_URL=redis://localhost:6379/0
```

---

## Health Check

ตรวจสอบว่าทุกอย่างพร้อมก่อนรัน bot:

```bash
python health_check.py
```

Health check จะตรวจสอบ:
- ✅ Python version (3.8+)
- ✅ Required packages installed
- ✅ .env file exists and configured
- ✅ Telegram bot token valid
- ✅ Redis connection
- ✅ FastAPI backend connectivity

**ตัวอย่าง Output:**

```
🏥 Hospital Booking Telegram Bot - Health Check
================================================================

🔍 Checking Python Version... ✅ Python 3.11 ✓
🔍 Checking Dependencies... ✅ All dependencies installed ✓
🔍 Checking Environment File... ✅ Environment variables configured ✓
🔍 Checking Telegram Token... ✅ Telegram bot token configured ✓
🔍 Checking Redis Connection... ✅ Redis connected at redis://localhost:6379/0 ✓
🔍 Checking FastAPI Backend... ✅ FastAPI connected (5 event types found) ✓

================================================================
📊 Health Check Summary
================================================================
✅ PASS - Python Version
✅ PASS - Dependencies
✅ PASS - Environment File
✅ PASS - Telegram Token
✅ PASS - Redis Connection
✅ PASS - FastAPI Backend

Passed: 6/6

🎉 All checks passed! Bot is ready to run.

To start the bot:
    python bot.py
```

---

## Running Tests

### Unit Tests

#### Test Validators

```bash
# Run validator tests
pytest tests/test_validators.py -v

# Run specific test class
pytest tests/test_validators.py::TestPhoneValidation -v

# Run specific test
pytest tests/test_validators.py::TestPhoneValidation::test_valid_thai_phone_10_digits -v
```

**ตัวอย่าง Output:**
```
tests/test_validators.py::TestPhoneValidation::test_valid_thai_phone_10_digits PASSED
tests/test_validators.py::TestPhoneValidation::test_valid_phone_with_country_code_plus PASSED
tests/test_validators.py::TestEmailValidation::test_valid_email PASSED
...
```

### Integration Tests

#### Test API Client

```bash
# Run API tests (requires FastAPI running)
pytest tests/test_api_client.py -v

# Or run manually for detailed output
python tests/test_api_client.py
```

**ตัวอย่าง Output:**
```
🧪 Testing FastAPI Endpoints
============================================================

──────────────────────────────────────────────────────────
Testing: API Connection
──────────────────────────────────────────────────────────
✅ API Connection OK - Found 5 event types

──────────────────────────────────────────────────────────
Testing: Get Event Types
──────────────────────────────────────────────────────────

📋 Event Types (5):
  - ตรวจสุขภาพทั่วไป (ID: 1)
  - ฉีดวัคซีน (ID: 2)
  - ตรวจเลือด (ID: 3)
  ...

============================================================
📊 Test Summary
============================================================
✅ PASS - API Connection
✅ PASS - Get Event Types
✅ PASS - Get Availability
✅ PASS - Search Booking

Passed: 4/4
```

#### Test Redis Connection

```bash
# Run Redis tests (requires Redis running)
pytest tests/test_redis.py -v

# Or run manually
python tests/test_redis.py
```

**ตัวอย่าง Output:**
```
🧪 Testing Redis Connection and Auth Service
============================================================

──────────────────────────────────────────────────────────
Testing: Redis Connection
──────────────────────────────────────────────────────────
✅ Redis connection successful

──────────────────────────────────────────────────────────
Testing: User Registration
──────────────────────────────────────────────────────────
✅ User registration successful
   User data: {'telegram_id': 123456789, 'name': 'Test User', ...}

============================================================
📊 Test Summary
============================================================
✅ PASS - Redis Connection
✅ PASS - User Registration
✅ PASS - User Retrieval
✅ PASS - Is Registered Check
✅ PASS - Session Management
✅ PASS - User Update

Passed: 6/6
🎉 All tests passed!
```

### Run All Tests

```bash
# Run all tests with pytest
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html

# Run only fast tests (exclude slow)
pytest -m "not slow" -v
```

---

## Manual Testing

### 1. Quick Start with Script

```bash
./start_bot.sh
```

This script will:
1. Activate virtual environment
2. Check .env file
3. Run health check
4. Start the bot if all checks pass

### 2. Manual Bot Testing

```bash
# Start bot manually
python bot.py
```

### 3. Test Flow in Telegram

#### A. Registration Flow

1. เปิด Telegram หา bot ของคุณ
2. พิมพ์ `/start`
3. กรอกชื่อ-นามสกุล (เช่น "สมชาย ใจดี")
4. กดแชร์เบอร์โทร หรือพิมพ์ (เช่น "0812345678")
5. ตรวจสอบว่าได้ main menu

**Expected Output:**
```
✅ ลงทะเบียนสำเร็จ!

👤 ชื่อ: สมชาย ใจดี
📱 เบอร์โทร: 0812345678

คุณสามารถเริ่มใช้งานระบบได้แล้ว
```

#### B. Booking Flow

1. กด "📅 จองนัด" หรือพิมพ์ `/book`
2. เลือกบริการ (เช่น "📋 ตรวจสุขภาพทั่วไป")
3. เลือกวันที่ (เช่น "📅 พรุ่งนี้ (23/11)")
4. เลือกเวลา (เช่น "🕐 10:00")
5. กดยืนยัน "✅ ยืนยัน"

**Expected Output:**
```
✅ จองนัดสำเร็จ!

🎫 รหัสการจอง: REF123456
📋 บริการ: ตรวจสุขภาพทั่วไป
📅 วันที่: 23 พฤศจิกายน 2568
🕐 เวลา: 10:00 น.
👨‍⚕️ แพทย์/พนักงาน: นพ.สมชาย

📍 สถานที่: คลินิกหมู่บ้านนอย
```

#### C. View Appointments

1. กด "📋 นัดหมายของฉัน" หรือพิมพ์ `/myappointments`
2. เห็นรายการนัดทั้งหมด
3. กดเลือกนัดเพื่อดูรายละเอียด
4. ทดสอบยกเลิกนัด (ถ้าต้องการ)

**Expected Output:**
```
📋 นัดหมายของคุณ (2 รายการ):
📅 2025-11-23 10:00 - ตรวจสุขภาพทั่วไป
📅 2025-11-25 14:30 - ฉีดวัคซีน
```

#### D. Error Handling Tests

ทดสอบ error cases:

1. **ยกเลิกระหว่างจอง:** พิมพ์ `/cancel` ระหว่าง booking flow
2. **จองวันที่ไม่มีเวลาว่าง:** เลือกวันที่ที่ไม่มี slots
3. **Unregistered user:** ใช้ account Telegram อื่นที่ยังไม่ลงทะเบียน

---

## Troubleshooting

### Bot ไม่ตอบ

1. ตรวจสอบว่า bot ทำงานอยู่:
   ```bash
   ps aux | grep bot.py
   ```

2. ตรวจสอบ logs:
   ```bash
   # ดู logs ล่าสุด
   tail -f bot.log
   ```

3. ตรวจสอบ token:
   ```bash
   echo $TELEGRAM_BOT_TOKEN
   ```

### API Connection Failed

1. ตรวจสอบ FastAPI:
   ```bash
   curl http://localhost:8000/api/v1/tenants/humnoi/event-types
   ```

2. ตรวจสอบ subdomain:
   ```bash
   # ใน .env
   DEFAULT_SUBDOMAIN=humnoi
   ```

### Redis Connection Failed

1. ตรวจสอบ Redis ทำงาน:
   ```bash
   redis-cli ping
   # ควรได้ PONG
   ```

2. ตรวจสอบ Redis URL:
   ```bash
   # ใน .env
   REDIS_URL=redis://localhost:6379/0
   ```

### Test Failures

1. **Import errors:**
   ```bash
   # ติดตั้ง dependencies ใหม่
   pip install -r requirements.txt
   ```

2. **Async test errors:**
   ```bash
   # ตรวจสอบ pytest-asyncio
   pip install pytest-asyncio
   ```

3. **Connection timeouts:**
   ```bash
   # เพิ่ม timeout ใน tests
   # หรือตรวจสอบว่า services ทำงาน
   ```

---

## Test Coverage

ตรวจสอบ test coverage:

```bash
# Install coverage
pip install pytest-cov

# Run with coverage report
pytest --cov=. --cov-report=term-missing

# Generate HTML report
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

---

## Continuous Testing

### Watch Mode (Auto-run tests on file changes)

```bash
# Install pytest-watch
pip install pytest-watch

# Run in watch mode
ptw -- -v
```

### Pre-commit Hook

สร้าง `.git/hooks/pre-commit`:

```bash
#!/bin/bash
echo "Running tests before commit..."
pytest
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

```bash
chmod +x .git/hooks/pre-commit
```

---

## คำแนะนำเพิ่มเติม

1. **รันทดสอบบ่อยๆ** - รัน health check ก่อนทำงานทุกครั้ง
2. **ทดสอบแต่ละ feature** - ทดสอบทีละส่วนเมื่อเพิ่ม feature ใหม่
3. **Mock data** - ใช้ test data แทนข้อมูลจริงในการทดสอบ
4. **Clean up** - ลบ test data ใน Redis หลังทดสอบ
5. **Log everything** - เปิด logging level เป็น DEBUG เมื่อ debug

---

Happy Testing! 🧪
