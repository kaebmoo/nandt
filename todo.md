# Hospital Booking - Telegram Bot & MCP Server Integration Plan

## 📋 ภาพรวมโครงการ (Project Overview)

โครงการนี้มีเป้าหมาย 2 ส่วนหลัก:

### 1. Telegram Chatbot Integration
สร้าง Telegram Bot เพื่อให้ผู้ใช้สามารถ:
- ดูเวลาว่างสำหรับการจองนัด
- จองนัดหมาย
- ค้นหา/ดูรายละเอียดนัดหมาย
- ยกเลิกหรือเลื่อนนัด
- รับ notifications เมื่อมีการเปลี่ยนแปลง

### 2. MCP Server Implementation
แปลง FastAPI endpoints เป็น MCP (Model Context Protocol) Server เพื่อให้ LLM/AI Agent สามารถ:
- เข้าถึงข้อมูลการจองนัดผ่าน tools
- ช่วยผู้ใช้จัดการนัดหมายด้วย natural language
- ตอบคำถามเกี่ยวกับตารางนัด
- ทำงานร่วมกับ Claude/GPT และ AI assistants อื่นๆ

---

## 🏗️ สถาปัตยกรรมที่วางแผน (Planned Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interfaces                          │
├─────────────────────┬───────────────────┬───────────────────┤
│  Telegram Bot       │   MCP Client      │   Web Dashboard   │
│  (python-telegram)  │   (Claude/AI)     │   (Flask)         │
└──────────┬──────────┴─────────┬─────────┴──────────┬────────┘
           │                    │                    │
           ├────────────────────┴────────────────────┤
           │         FastAPI Backend                 │
           │    (hospital-booking/fastapi_app)       │
           └─────────────────┬───────────────────────┘
                             │
                    ┌────────┴─────────┐
                    │   PostgreSQL     │
                    │  (Multi-tenant)  │
                    └──────────────────┘
```

---

## 📦 Phase 1: Telegram Bot Integration

### 1.1 Environment Setup
- [ ] ติดตั้ง dependencies
  ```bash
  pip install python-telegram-bot==20.7
  pip install python-telegram-bot[webhooks]
  pip install httpx  # สำหรับเรียก FastAPI endpoints
  pip install python-dotenv
  ```

- [ ] สร้าง Telegram Bot ผ่าน BotFather
  - พิมพ์ `/newbot` ใน Telegram (@BotFather)
  - ตั้งชื่อ bot (เช่น "Hospital Booking Bot")
  - ได้ Bot Token (format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)
  - เก็บ token ไว้ใน `.env`

- [ ] สร้างโครงสร้าง directory
  ```
  hospital-booking/
  ├── telegram_bot/
  │   ├── __init__.py
  │   ├── bot.py              # Main bot application
  │   ├── handlers/
  │   │   ├── __init__.py
  │   │   ├── start.py        # /start command
  │   │   ├── booking.py      # Booking conversation
  │   │   ├── search.py       # Search appointments
  │   │   └── cancel.py       # Cancel/reschedule
  │   ├── services/
  │   │   ├── __init__.py
  │   │   ├── api_client.py   # FastAPI client wrapper
  │   │   └── auth.py         # User authentication
  │   ├── models/
  │   │   ├── __init__.py
  │   │   └── user_state.py   # Conversation state
  │   ├── utils/
  │   │   ├── __init__.py
  │   │   ├── keyboards.py    # Inline keyboards
  │   │   └── validators.py   # Input validation
  │   └── config.py
  └── .env
  ```

### 1.2 Core Bot Development

#### 1.2.1 Configuration (`telegram_bot/config.py`)
- [ ] โหลด environment variables
  ```python
  TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
  FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
  DEFAULT_SUBDOMAIN = os.getenv("DEFAULT_SUBDOMAIN", "demo")
  REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
  ```

#### 1.2.2 API Client (`telegram_bot/services/api_client.py`)
- [ ] สร้าง wrapper class สำหรับเรียก FastAPI
  ```python
  class HospitalBookingAPI:
      def __init__(self, base_url: str, subdomain: str):
          self.base_url = base_url
          self.subdomain = subdomain

      async def get_event_types(self) -> List[EventType]
      async def get_availability(self, event_type_id: int, date: str) -> List[TimeSlot]
      async def create_booking(self, booking_data: BookingCreate) -> BookingResponse
      async def search_booking(self, phone: str = None, email: str = None) -> List[Booking]
      async def cancel_booking(self, reference: str, reason: str) -> bool
      async def reschedule_booking(self, reference: str, new_date: str, new_time: str) -> bool
  ```

#### 1.2.3 User Authentication
- [ ] เชื่อมโยง Telegram user กับ hospital patient
  - เก็บ mapping: `telegram_user_id` -> `patient_info`
  - ใช้ Redis หรือ database table `telegram_users`
  ```sql
  CREATE TABLE public.telegram_users (
      id SERIAL PRIMARY KEY,
      telegram_id BIGINT UNIQUE NOT NULL,
      phone_number VARCHAR(20),
      email VARCHAR(255),
      name VARCHAR(255),
      hospital_id INTEGER REFERENCES hospitals(id),
      created_at TIMESTAMP DEFAULT NOW()
  );
  ```

- [ ] Implement phone verification
  - ขอเบอร์โทรจาก user
  - ส่ง OTP ผ่าน SMS (ใช้ `otp_service.py` ที่มีอยู่)
  - ยืนยัน OTP
  - Link telegram_id กับ phone

#### 1.2.4 Bot Handlers

**Start Handler** (`telegram_bot/handlers/start.py`)
- [ ] `/start` command
  - แสดงข้อความต้อนรับ
  - ตรวจสอบว่า user ลงทะเบียนแล้วหรือยัง
  - ถ้ายัง -> เริ่ม registration flow

- [ ] Registration conversation
  1. ขอชื่อ
  2. ขอเบอร์โทร (ใช้ Telegram phone sharing หรือพิมพ์เอง)
  3. ส่ง OTP
  4. ยืนยัน OTP
  5. เสร็จสิ้น -> แสดง main menu

**Booking Handler** (`telegram_bot/handlers/booking.py`)
- [ ] `/book` command - เริ่ม booking flow
  1. แสดง event types (บริการที่มี)
  2. เลือก event type
  3. เลือกวันที่ (inline calendar)
  4. แสดง available time slots
  5. เลือกเวลา
  6. ยืนยันข้อมูล
  7. สร้างการจอง
  8. แสดง booking reference

- [ ] สร้าง inline keyboard สำหรับ:
  - Event type selection
  - Date picker (calendar)
  - Time slot selection
  - Confirmation (Yes/No)

**Search Handler** (`telegram_bot/handlers/search.py`)
- [ ] `/myappointments` command
  - ดึงนัดหมายทั้งหมดของ user
  - แสดงเป็น list พร้อม inline buttons
  - กด booking แต่ละตัวเพื่อดูรายละเอียด

- [ ] Appointment details view
  - แสดง: วันที่, เวลา, บริการ, หมอ/พนักงาน
  - Buttons: [Reschedule] [Cancel] [Back]

**Cancel/Reschedule Handler** (`telegram_bot/handlers/cancel.py`)
- [ ] Cancel flow
  1. ยืนยัน "แน่ใจไหมที่จะยกเลิก?"
  2. ถามเหตุผล (optional)
  3. เรียก API cancel
  4. แสดงผลสำเร็จ/ล้มเหลว

- [ ] Reschedule flow
  1. แสดงวันที่ที่ available
  2. เลือกวันใหม่
  3. แสดง time slots
  4. เลือกเวลาใหม่
  5. ยืนยัน
  6. เรียก API reschedule
  7. แสดง confirmation

#### 1.2.5 Conversation State Management
- [ ] ใช้ `ConversationHandler` ของ python-telegram-bot
- [ ] เก็บ state ด้วย Redis (persistent storage)
  ```python
  from telegram.ext import ConversationHandler, CommandHandler, MessageHandler

  # States
  SELECTING_SERVICE, SELECTING_DATE, SELECTING_TIME, CONFIRMING = range(4)

  booking_conv = ConversationHandler(
      entry_points=[CommandHandler('book', start_booking)],
      states={
          SELECTING_SERVICE: [CallbackQueryHandler(service_selected)],
          SELECTING_DATE: [CallbackQueryHandler(date_selected)],
          SELECTING_TIME: [CallbackQueryHandler(time_selected)],
          CONFIRMING: [CallbackQueryHandler(confirm_booking)],
      },
      fallbacks=[CommandHandler('cancel', cancel_booking)]
  )
  ```

### 1.3 UI/UX Features

- [ ] Inline Keyboards
  - Service selection grid
  - Calendar picker (7-day or monthly view)
  - Time slots buttons
  - Quick actions (Cancel, Reschedule)

- [ ] Rich Messages
  - ใช้ Markdown/HTML formatting
  - แสดง emoji icons (📅 🕐 ✅ ❌)
  - สรุปข้อมูลการจองอย่างชัดเจน

- [ ] Error Handling
  - จัดการ API errors
  - แสดงข้อความเป็นภาษาไทย
  - Fallback options เมื่อเกิด error

- [ ] Notifications
  - แจ้งเตือนก่อนนัด 1 วัน (ใช้ background worker)
  - แจ้งเตือนเมื่อมีการเปลี่ยนแปลงนัด

### 1.4 Testing & Deployment

- [ ] Unit tests
  - Test handlers แยกส่วน
  - Mock API calls

- [ ] Integration tests
  - Test end-to-end booking flow
  - Test cancel/reschedule

- [ ] Deployment
  - **Option 1: Polling** (ง่าย, สำหรับ development)
    ```python
    application.run_polling()
    ```

  - **Option 2: Webhook** (production, efficient)
    - ตั้ง webhook URL: `https://yourdomain.com/telegram/webhook`
    - เพิ่ม endpoint ใน FastAPI:
      ```python
      @app.post("/telegram/webhook")
      async def telegram_webhook(update: dict):
          # Process update
      ```

- [ ] Production setup
  - ใช้ systemd service หรือ Docker
  - Monitor with logging
  - Handle rate limiting (Telegram API limits)

---

## 🔌 Phase 2: MCP Server Implementation

### 2.1 Understanding MCP (Model Context Protocol)

MCP ช่วยให้ LLM เข้าถึง:
- **Resources**: Static data (files, docs)
- **Tools**: Dynamic actions (API calls, database queries)
- **Prompts**: Reusable templates

เราจะสร้าง MCP server ที่ expose FastAPI endpoints เป็น **Tools**

### 2.2 Environment Setup

- [ ] ติดตั้ง MCP SDK
  ```bash
  pip install mcp
  # หรือ
  npm install @modelcontextprotocol/sdk  # ถ้าใช้ TypeScript
  ```

- [ ] สร้างโครงสร้าง directory
  ```
  hospital-booking/
  ├── mcp_server/
  │   ├── __init__.py
  │   ├── server.py           # MCP server entry point
  │   ├── tools/
  │   │   ├── __init__.py
  │   │   ├── booking_tools.py
  │   │   ├── availability_tools.py
  │   │   └── search_tools.py
  │   ├── resources/
  │   │   ├── __init__.py
  │   │   └── schemas.py      # API schemas as resources
  │   └── config.py
  ```

### 2.3 Core MCP Server Development

#### 2.3.1 Server Setup (`mcp_server/server.py`)

- [ ] สร้าง MCP server instance
  ```python
  from mcp.server import Server
  from mcp.server.stdio import stdio_server

  server = Server("hospital-booking-mcp")

  @server.list_tools()
  async def list_tools():
      return [
          Tool(
              name="check_availability",
              description="Check available time slots for booking",
              inputSchema={...}
          ),
          Tool(name="create_booking", ...),
          Tool(name="search_appointments", ...),
          Tool(name="cancel_booking", ...),
          Tool(name="reschedule_booking", ...),
          Tool(name="get_event_types", ...),
      ]

  @server.call_tool()
  async def call_tool(name: str, arguments: dict):
      # Route to appropriate tool handler
      if name == "check_availability":
          return await check_availability_tool(arguments)
      elif name == "create_booking":
          return await create_booking_tool(arguments)
      # ...

  if __name__ == "__main__":
      async with stdio_server() as (read, write):
          await server.run(read, write)
  ```

#### 2.3.2 Booking Tools (`mcp_server/tools/booking_tools.py`)

- [ ] **check_availability** tool
  ```python
  async def check_availability_tool(args: dict):
      """
      Check available time slots for a specific service and date

      Args:
          subdomain: str - Hospital subdomain
          event_type_id: int - Service ID
          date: str - Date in YYYY-MM-DD format

      Returns:
          List of available time slots with provider info
      """
      # Call FastAPI GET /api/v1/tenants/{subdomain}/booking/availability/{event_type_id}
      # Return formatted results
  ```

- [ ] **create_booking** tool
  ```python
  async def create_booking_tool(args: dict):
      """
      Create a new appointment booking

      Args:
          subdomain: str
          event_type_id: int
          date: str (YYYY-MM-DD)
          time: str (HH:MM)
          guest_name: str
          guest_email: str (optional)
          guest_phone: str (optional)
          notes: str (optional)

      Returns:
          Booking reference and confirmation details
      """
      # Call FastAPI POST /api/v1/tenants/{subdomain}/booking/create
  ```

- [ ] **cancel_booking** tool
  ```python
  async def cancel_booking_tool(args: dict):
      """
      Cancel an existing appointment

      Args:
          subdomain: str
          booking_reference: str
          reason: str (optional)

      Returns:
          Success status and message
      """
  ```

- [ ] **reschedule_booking** tool
  ```python
  async def reschedule_booking_tool(args: dict):
      """
      Reschedule an appointment to new date/time

      Args:
          subdomain: str
          booking_reference: str
          new_date: str
          new_time: str
          reason: str (optional)

      Returns:
          Updated booking details
      """
  ```

#### 2.3.3 Search Tools (`mcp_server/tools/search_tools.py`)

- [ ] **search_appointments** tool
  ```python
  async def search_appointments_tool(args: dict):
      """
      Search appointments by email, phone, or reference

      Args:
          subdomain: str
          email: str (optional)
          phone: str (optional)
          booking_reference: str (optional)

      Returns:
          List of matching appointments
      """
  ```

- [ ] **get_event_types** tool
  ```python
  async def get_event_types_tool(args: dict):
      """
      Get all available services/event types

      Args:
          subdomain: str

      Returns:
          List of services with details (name, duration, description)
      """
  ```

#### 2.3.4 Resources (`mcp_server/resources/schemas.py`)

- [ ] Expose API schemas as MCP resources
  ```python
  @server.list_resources()
  async def list_resources():
      return [
          Resource(
              uri="schema://event-types",
              name="Event Types Schema",
              mimeType="application/json"
          ),
          Resource(
              uri="schema://booking",
              name="Booking Schema",
              mimeType="application/json"
          ),
      ]

  @server.read_resource()
  async def read_resource(uri: str):
      if uri == "schema://event-types":
          return json.dumps(EventTypeResponse.schema())
      # ...
  ```

### 2.4 Authentication & Security

- [ ] API Key authentication
  - เพิ่ม API key requirement ใน FastAPI
  ```python
  from fastapi import Header, HTTPException

  async def verify_api_key(x_api_key: str = Header(...)):
      if x_api_key not in VALID_API_KEYS:
          raise HTTPException(status_code=401, detail="Invalid API key")
      return x_api_key

  @app.get("/api/v1/tenants/{subdomain}/booking/...", dependencies=[Depends(verify_api_key)])
  ```

- [ ] MCP server config
  - เก็บ API keys ไว้ใน `mcp_server/config.py`
  - ส่งไปกับทุก API request

### 2.5 Testing MCP Server

- [ ] Local testing กับ Claude Desktop
  1. เพิ่ม config ใน `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
     ```json
     {
       "mcpServers": {
         "hospital-booking": {
           "command": "python",
           "args": ["/path/to/hospital-booking/mcp_server/server.py"],
           "env": {
             "FASTAPI_BASE_URL": "http://localhost:8000"
           }
         }
       }
     }
     ```

  2. รีสตาร์ท Claude Desktop
  3. ทดสอบด้วย prompts:
     - "Check available time slots for general checkup on 2025-11-25 at humnoi hospital"
     - "Book an appointment for me at 10:00 AM"
     - "Search my appointments"

- [ ] Unit tests
  - Test แต่ละ tool function
  - Mock FastAPI responses

- [ ] Integration tests
  - Test end-to-end กับ FastAPI จริง

### 2.6 Advanced Features

- [ ] **Prompts** (reusable templates)
  ```python
  @server.list_prompts()
  async def list_prompts():
      return [
          Prompt(
              name="book-appointment",
              description="Guide user through booking process",
              arguments=[
                  PromptArgument(name="service_type", description="Type of service", required=False)
              ]
          )
      ]

  @server.get_prompt()
  async def get_prompt(name: str, arguments: dict):
      if name == "book-appointment":
          service = arguments.get("service_type", "any service")
          return f"""Help the user book a hospital appointment for {service}.

          Steps:
          1. Ask for their preferred date
          2. Check availability using check_availability tool
          3. Show available time slots
          4. Confirm their choice
          5. Create booking using create_booking tool
          6. Provide booking reference
          """
  ```

- [ ] **Sampling** (AI-initiated actions)
  - ให้ MCP server suggest actions based on context

- [ ] **Progress notifications**
  - แจ้งสถานะเมื่อ tools ทำงานนาน

### 2.7 Deployment

- [ ] Standalone MCP server
  - Deploy แยกจาก FastAPI
  - Run as systemd service or Docker container

- [ ] Claude for Work integration
  - Publish to organization's MCP registry
  - Team members สามารถใช้ tools ร่วมกัน

- [ ] Documentation
  - เขียน README สำหรับการ setup
  - Document แต่ละ tool พร้อม examples

---

## 🔄 Phase 3: Enhanced FastAPI for Better Integration

### 3.1 API Improvements

- [ ] เพิ่ม API Key authentication middleware
  ```python
  @app.middleware("http")
  async def verify_api_key_middleware(request: Request, call_next):
      if request.url.path.startswith("/api/v1"):
          api_key = request.headers.get("X-API-Key")
          if not api_key or api_key not in VALID_API_KEYS:
              return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
      return await call_next(request)
  ```

- [ ] Rate limiting (ป้องกัน abuse)
  ```bash
  pip install slowapi
  ```
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)

  @app.get("/api/v1/tenants/{subdomain}/booking/...")
  @limiter.limit("100/hour")
  async def get_availability(...):
  ```

- [ ] Webhook support (สำหรับ notifications)
  - เพิ่ม endpoint รับ webhook registrations
  - ส่ง webhook เมื่อมีการเปลี่ยนแปลง booking
  ```python
  @app.post("/api/v1/webhooks/register")
  async def register_webhook(webhook_url: str, events: List[str]):
      # Save webhook subscription

  # ส่ง notification เมื่อ booking created/cancelled/rescheduled
  async def send_webhook(event: str, data: dict):
      for webhook in active_webhooks:
          if event in webhook.events:
              async with httpx.AsyncClient() as client:
                  await client.post(webhook.url, json={"event": event, "data": data})
  ```

### 3.2 Database Extensions

- [ ] สร้าง table สำหรับ Telegram users
  ```sql
  CREATE TABLE public.telegram_users (
      id SERIAL PRIMARY KEY,
      telegram_id BIGINT UNIQUE NOT NULL,
      telegram_username VARCHAR(255),
      phone_number VARCHAR(20),
      email VARCHAR(255),
      name VARCHAR(255),
      hospital_id INTEGER REFERENCES hospitals(id),
      is_verified BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP DEFAULT NOW(),
      last_active TIMESTAMP DEFAULT NOW()
  );
  ```

- [ ] สร้าง table สำหรับ API keys
  ```sql
  CREATE TABLE public.api_keys (
      id SERIAL PRIMARY KEY,
      key_hash VARCHAR(255) UNIQUE NOT NULL,
      name VARCHAR(255),
      hospital_id INTEGER REFERENCES hospitals(id),
      scopes TEXT[], -- ['read:bookings', 'write:bookings']
      is_active BOOLEAN DEFAULT TRUE,
      created_at TIMESTAMP DEFAULT NOW(),
      last_used TIMESTAMP
  );
  ```

- [ ] สร้าง table สำหรับ webhooks
  ```sql
  CREATE TABLE public.webhooks (
      id SERIAL PRIMARY KEY,
      url TEXT NOT NULL,
      events TEXT[], -- ['booking.created', 'booking.cancelled']
      hospital_id INTEGER REFERENCES hospitals(id),
      secret VARCHAR(255),
      is_active BOOLEAN DEFAULT TRUE,
      created_at TIMESTAMP DEFAULT NOW()
  );
  ```

### 3.3 Background Tasks

- [ ] Scheduled notifications
  - ใช้ Celery beat สำหรับส่ง reminders
  ```python
  @celery.task
  def send_appointment_reminders():
      tomorrow = date.today() + timedelta(days=1)
      appointments = get_appointments_for_date(tomorrow)
      for apt in appointments:
          if apt.patient.telegram_id:
              send_telegram_message(apt.patient.telegram_id, reminder_text)
  ```

- [ ] Webhook delivery queue
  - ใช้ RQ/Celery สำหรับส่ง webhooks แบบ async

---

## 📊 Phase 4: Monitoring & Analytics

### 4.1 Logging

- [ ] Structured logging
  ```python
  import structlog

  logger = structlog.get_logger()
  logger.info("booking_created", booking_ref=ref, user_id=user_id, event_type=event_type)
  ```

- [ ] Log aggregation
  - ใช้ Loki หรือ ELK stack
  - Track API usage, errors, performance

### 4.2 Metrics

- [ ] Prometheus metrics
  ```bash
  pip install prometheus-fastapi-instrumentator
  ```
  ```python
  from prometheus_fastapi_instrumentator import Instrumentator

  Instrumentator().instrument(app).expose(app)
  ```

- [ ] Custom metrics
  - Booking success rate
  - Average response time
  - Telegram bot active users
  - MCP tool usage frequency

### 4.3 Error Tracking

- [ ] Sentry integration
  ```bash
  pip install sentry-sdk
  ```
  ```python
  import sentry_sdk
  sentry_sdk.init(dsn="...", traces_sample_rate=1.0)
  ```

---

## 🧪 Phase 5: Testing Strategy

### 5.1 Unit Tests
- [ ] FastAPI endpoints tests
- [ ] Telegram bot handlers tests
- [ ] MCP tools tests

### 5.2 Integration Tests
- [ ] End-to-end booking flow (Telegram)
- [ ] End-to-end booking flow (MCP)
- [ ] API key authentication
- [ ] Webhook delivery

### 5.3 Load Testing
- [ ] Test API performance under load
  ```bash
  pip install locust
  ```
- [ ] Test Telegram bot with multiple concurrent users

---

## 📝 Documentation Requirements

- [ ] **API Documentation**
  - Swagger/OpenAPI (FastAPI auto-generates)
  - Authentication guide
  - Rate limiting policies

- [ ] **Telegram Bot User Guide**
  - How to register
  - How to book appointments
  - FAQ

- [ ] **MCP Server Guide**
  - Installation instructions
  - Available tools reference
  - Example prompts for Claude

- [ ] **Developer Guide**
  - Architecture overview
  - Local development setup
  - Deployment instructions

---

## 🚀 Deployment Checklist

### Telegram Bot
- [ ] Production server setup (VPS/Cloud)
- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] Bot webhook configured (if using webhooks)
- [ ] Monitoring setup
- [ ] Backup strategy

### MCP Server
- [ ] Claude Desktop config documented
- [ ] API keys generated and distributed
- [ ] HTTPS endpoint configured (if remote MCP)
- [ ] Usage documentation published

### FastAPI Enhancements
- [ ] API keys table populated
- [ ] Rate limiting configured
- [ ] Webhooks tested
- [ ] SSL certificates installed

---

## 📋 Timeline Estimate (ไม่รวมเวลา testing ละเอียด)

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1: Telegram Bot | Core bot + booking flow | ⭐⭐⭐ Medium-High |
| Phase 2: MCP Server | Tools + resources | ⭐⭐ Medium |
| Phase 3: FastAPI Enhancement | Auth + webhooks | ⭐⭐ Medium |
| Phase 4: Monitoring | Logging + metrics | ⭐ Low |
| Phase 5: Testing | Unit + integration tests | ⭐⭐ Medium |

---

## 🎯 Success Metrics

### Telegram Bot
- [ ] Users can book appointments without visiting website
- [ ] <5 second response time for availability checks
- [ ] >95% successful booking completion rate
- [ ] <2% error rate

### MCP Server
- [ ] Claude can successfully check availability
- [ ] Claude can create bookings via natural language
- [ ] All tools respond within 3 seconds
- [ ] Clear error messages for failed operations

---

## 🔗 Resources & References

### Telegram Bot Development
- [python-telegram-bot documentation](https://python-telegram-bot.readthedocs.io/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [ConversationHandler guide](https://github.com/python-telegram-bot/python-telegram-bot/wiki/ConversationHandler)

### MCP (Model Context Protocol)
- [MCP Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude MCP Documentation](https://docs.anthropic.com/claude/docs/model-context-protocol)

### FastAPI
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Authentication tutorial](https://fastapi.tiangolo.com/tutorial/security/)
- [Background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

---

## 🚦 Getting Started - Quick Start Guide

### 1. Start with Telegram Bot MVP
```bash
cd hospital-booking
mkdir telegram_bot
cd telegram_bot

# สร้าง virtual environment
python -m venv venv
source venv/bin/activate

# ติดตั้ง dependencies
pip install python-telegram-bot httpx python-dotenv redis

# สร้างไฟล์ .env
echo "TELEGRAM_BOT_TOKEN=your_token_here" > .env
echo "FASTAPI_BASE_URL=http://localhost:8000" >> .env

# สร้างไฟล์ bot.py ตามโครงสร้างด้านบน
# ...

# Run bot
python bot.py
```

### 2. Then Build MCP Server
```bash
cd hospital-booking
mkdir mcp_server
cd mcp_server

pip install mcp httpx

# สร้างไฟล์ server.py ตามโครงสร้างด้านบน
# ...

# Test locally
python server.py
```

---

## 📞 Support & Questions

หากมีคำถามหรือติดปัญหาระหว่างพัฒนา:
1. ตรวจสอบ logs (/var/log/telegram_bot.log, /var/log/fastapi.log)
2. ทดสอบ API endpoints ด้วย Postman/curl ก่อน
3. ใช้ Telegram Bot API debug mode
4. ตรวจสอบ MCP server logs ใน Claude Desktop

---

**หมายเหตุ:** แผนนี้เป็น roadmap ที่ครอบคลุม สามารถปรับแต่งตามความต้องการและ priority ของโครงการได้
