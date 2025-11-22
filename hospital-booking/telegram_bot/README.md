# Hospital Booking Telegram Bot

Telegram chatbot สำหรับระบบจองนัดหมาย Hospital Booking System

## ฟีเจอร์หลัก

- ✅ ลงทะเบียนผู้ใช้ผ่าน Telegram
- 📅 จองนัดหมายผ่าน conversational interface
- 🔍 ค้นหาและดูนัดหมายของตัวเอง
- ❌ ยกเลิกนัดหมาย
- 📱 รองรับภาษาไทย
- 💾 เก็บข้อมูล session ด้วย Redis

## สถาปัตยกรรม

```
telegram_bot/
├── bot.py                  # Main entry point
├── config.py              # Configuration & constants
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
│
├── handlers/             # Command handlers
│   ├── start.py         # /start & registration
│   ├── booking.py       # /book conversation flow
│   └── search.py        # /myappointments
│
├── services/            # Business logic
│   ├── api_client.py    # FastAPI client wrapper
│   └── auth.py          # User authentication
│
├── utils/               # Utilities
│   ├── keyboards.py     # Inline keyboards
│   └── validators.py    # Input validation
│
└── models/              # Data models (future)
```

## การติดตั้ง

### 1. สร้าง Telegram Bot

1. ค้นหา @BotFather ใน Telegram
2. ส่ง `/newbot`
3. ตั้งชื่อ bot (เช่น "Hospital Booking Bot")
4. เก็บ Bot Token ที่ได้รับ

### 2. ติดตั้ง Dependencies

```bash
cd telegram_bot

# สร้าง virtual environment (แนะนำ)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# หรือ
.\venv\Scripts\activate   # Windows

# ติดตั้ง packages
pip install -r requirements.txt
```

### 3. ตั้งค่า Environment Variables

```bash
# Copy template
cp .env.example .env

# แก้ไขค่าใน .env
nano .env
```

ตั้งค่าตัวแปรต่อไปนี้:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
FASTAPI_BASE_URL=http://localhost:8000
DEFAULT_SUBDOMAIN=humnoi
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 4. เริ่มต้น Redis (ถ้ายังไม่มี)

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# หรือใช้ Docker
docker run -d -p 6379:6379 redis:alpine
```

### 5. เริ่มต้น FastAPI Backend

ตรวจสอบว่า FastAPI backend ทำงานอยู่:

```bash
cd ../fastapi_app
uvicorn app.main:app --reload --port 8000
```

### 6. รัน Bot

```bash
cd telegram_bot
python bot.py
```

คุณควรเห็นข้อความ:
```
Bot is running. Press Ctrl+C to stop.
```

## การใช้งาน

### คำสั่งหลัก

| คำสั่ง | คำอธิบาย |
|--------|---------|
| `/start` | เริ่มต้นใช้งาน / ลงทะเบียนผู้ใช้ใหม่ |
| `/book` | จองนัดหมาย |
| `/myappointments` | ดูนัดหมายทั้งหมด |
| `/help` | แสดงคำสั่งที่ใช้งานได้ |
| `/cancel` | ยกเลิกการทำงานปัจจุบัน |

### การจองนัด (Booking Flow)

1. พิมพ์ `/book` หรือกด "📅 จองนัด"
2. เลือกบริการที่ต้องการ (เช่น ตรวจสุขภาพทั่วไป)
3. เลือกวันที่
4. เลือกเวลาที่ว่าง
5. ยืนยันข้อมูล
6. ได้รับรหัสการจอง (Booking Reference)

### การดูนัดหมาย

1. พิมพ์ `/myappointments` หรือกด "📋 นัดหมายของฉัน"
2. เห็นรายการนัดทั้งหมด
3. กดเลือกนัดเพื่อดูรายละเอียด
4. สามารถยกเลิกนัดได้

## โครงสร้างข้อมูล

### User Data (Redis)

```json
{
  "telegram_id": 123456789,
  "name": "สมชาย ใจดี",
  "phone": "0812345678",
  "email": null,
  "username": "somchai_user",
  "is_registered": true
}
```

### Session Data (Redis)

```json
{
  "booking": {
    "service_id": 1,
    "service_name": "ตรวจสุขภาพทั่วไป",
    "date": "2025-11-25",
    "time": "10:00",
    "provider_id": 5
  }
}
```

## การพัฒนา

### เพิ่ม Handler ใหม่

1. สร้างไฟล์ใน `handlers/` (เช่น `reminder.py`)
2. เขียน handler functions
3. สร้าง ConversationHandler (ถ้าจำเป็น)
4. Register ใน `bot.py`

```python
# handlers/reminder.py
async def set_reminder(update, context):
    # Your code here
    pass

# bot.py
from handlers.reminder import set_reminder
application.add_handler(CommandHandler("reminder", set_reminder))
```

### เพิ่ม API Endpoint

แก้ไขไฟล์ `services/api_client.py`:

```python
async def get_providers(self) -> List[Dict[str, Any]]:
    endpoint = self._get_endpoint("providers")
    return await self._request("GET", endpoint)
```

### การทดสอบ

```bash
# ติดตั้ง pytest
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

## Production Deployment

### Option 1: Polling (แนะนำสำหรับเริ่มต้น)

```bash
# ใช้ systemd
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Hospital Booking Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/telegram_bot
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

### Option 2: Webhooks (แนะนำสำหรับ production)

1. ตั้งค่า HTTPS endpoint
2. แก้ไข `bot.py` เพื่อใช้ webhooks:

```python
# Instead of run_polling()
application.run_webhook(
    listen="0.0.0.0",
    port=8443,
    url_path="telegram",
    webhook_url="https://yourdomain.com/telegram"
)
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

```bash
docker build -t telegram-bot .
docker run -d --name telegram-bot --env-file .env telegram-bot
```

## Monitoring & Logging

### ดู Logs

```bash
# Development
python bot.py  # Logs จะแสดงใน console

# Production (systemd)
sudo journalctl -u telegram-bot -f

# Production (Docker)
docker logs -f telegram-bot
```

### Error Tracking

พิจารณาใช้ Sentry สำหรับ error tracking:

```bash
pip install sentry-sdk
```

```python
# bot.py
import sentry_sdk
sentry_sdk.init(dsn="your_dsn_here")
```

## Troubleshooting

### Bot ไม่ตอบสนอง

1. ตรวจสอบ Bot Token ใน `.env`
2. ตรวจสอบว่า FastAPI backend ทำงาน
3. ตรวจสอบ Redis connection

```bash
# Test Redis
redis-cli ping  # ควรได้ PONG
```

### API Errors

1. ตรวจสอบ `FASTAPI_BASE_URL` และ `DEFAULT_SUBDOMAIN`
2. ทดสอบ API endpoints ด้วย curl:

```bash
curl http://localhost:8000/api/v1/tenants/humnoi/event-types
```

### Redis Connection Failed

```bash
# ตรวจสอบว่า Redis ทำงาน
sudo systemctl status redis

# หรือ
redis-cli ping
```

## ฟีเจอร์ที่จะพัฒนาต่อ

- [ ] OTP verification สำหรับ registration
- [ ] Reschedule appointments
- [ ] Push notifications (reminders)
- [ ] Multi-language support
- [ ] Admin commands
- [ ] Analytics dashboard
- [ ] Payment integration
- [ ] Feedback system

## License

MIT License

## ผู้พัฒนา

Hospital Booking System Development Team

## การสนับสนุน

หากมีปัญหาหรือข้อสงสัย:
- เปิด Issue บน GitHub
- ติดต่อทีมพัฒนา
