# Hospital Booking MCP Server

MCP (Model Context Protocol) Server สำหรับระบบจองนัดหมาย Hospital Booking System

ให้ AI agents (Claude, GPT, etc.) สามารถจัดการการจองนัดหมายผ่าน natural language

## ภาพรวม

MCP Server นี้ expose tools ต่อไปนี้ให้กับ AI agents:

| Tool | Description |
|------|-------------|
| `check_availability` | ตรวจสอบเวลาว่างสำหรับการจอง |
| `get_event_types` | ดูรายการบริการทั้งหมด |
| `create_booking` | จองนัดหมายใหม่ |
| `search_appointments` | ค้นหานัดหมาย |
| `cancel_booking` | ยกเลิกนัดหมาย |
| `reschedule_booking` | เลื่อนนัดหมาย |

## โครงสร้างไฟล์

```
mcp_server/
├── server.py           # Main MCP server
├── config.py          # Configuration
├── requirements.txt   # Python dependencies
├── .env.example      # Environment template
├── README.md         # This file
│
├── tools/            # MCP Tools
│   └── booking_tools.py
│
└── resources/        # MCP Resources (future)
```

## การติดตั้ง

### 1. ติดตั้ง Dependencies

```bash
cd mcp_server

# สร้าง virtual environment
python -m venv venv
source venv/bin/activate

# ติดตั้ง packages
pip install -r requirements.txt
```

### 2. ตั้งค่า Environment

```bash
# Copy template
cp .env.example .env

# แก้ไข .env
nano .env
```

ตั้งค่าตัวแปร:
```env
FASTAPI_BASE_URL=http://localhost:8000
DEFAULT_SUBDOMAIN=humnoi
LOG_LEVEL=INFO
```

### 3. เริ่มต้น FastAPI Backend

ตรวจสอบว่า FastAPI backend ทำงานอยู่:

```bash
cd ../fastapi_app
uvicorn app.main:app --reload --port 8000
```

## การใช้งานกับ Claude Desktop

### 1. เพิ่ม Configuration

เปิดไฟล์ config:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

เพิ่ม MCP server:

```json
{
  "mcpServers": {
    "hospital-booking": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_server/server.py"],
      "env": {
        "FASTAPI_BASE_URL": "http://localhost:8000",
        "DEFAULT_SUBDOMAIN": "humnoi"
      }
    }
  }
}
```

**⚠️ Important:**
- ใช้ **absolute path** ไม่ใช่ relative path
- เปลี่ยน `/absolute/path/to/` เป็น path จริงของคุณ
- ตรวจสอบว่า Python path ถูกต้อง (ใช้ `which python` เพื่อหา path)

### 2. รีสตาร์ท Claude Desktop

- ปิด Claude Desktop ให้หมด
- เปิดใหม่

### 3. ทดสอบ MCP Tools

หลังจากรีสตาร์ท คุณจะเห็น hammer icon (🔨) ที่มุมขวาล่าง

ทดสอบด้วย prompts:

```
User: Check available time slots for general checkup on 2025-11-25 at humnoi hospital
```

```
User: Show me all services available for booking
```

```
User: Create a booking for me - name: John Doe, phone: 0812345678, service: general checkup, date: 2025-11-25, time: 10:00
```

## การทดสอบแบบ Standalone

### Test Server Locally

```bash
python server.py
```

Server จะทำงานใน stdio mode (รอ input จาก MCP client)

### Manual Testing (ไม่แนะนำ)

สำหรับการทดสอบ tools โดยตรง สามารถสร้าง test script:

```python
# test_tools.py
import asyncio
from tools.booking_tools import BookingTools

async def main():
    tools = BookingTools("http://localhost:8000", "humnoi")

    # Test get event types
    result = await tools.get_event_types("humnoi")
    print(result)

    # Test check availability
    result = await tools.check_availability("humnoi", 1, "2025-11-25")
    print(result)

    await tools.close()

asyncio.run(main())
```

## Tools Reference

### check_availability

ตรวจสอบเวลาว่างสำหรับการจอง

**Parameters:**
- `subdomain` (string, required): Hospital subdomain
- `event_type_id` (integer, required): Service ID
- `date` (string, required): Date in YYYY-MM-DD format

**Example:**
```json
{
  "subdomain": "humnoi",
  "event_type_id": 1,
  "date": "2025-11-25"
}
```

**Response:**
```json
{
  "success": true,
  "date": "2025-11-25",
  "event_type_id": 1,
  "available_slots": 8,
  "slots": [
    {
      "time": "09:00",
      "provider_name": "Dr. Smith",
      "provider_id": 1
    },
    ...
  ]
}
```

### get_event_types

ดูรายการบริการทั้งหมด

**Parameters:**
- `subdomain` (string, required): Hospital subdomain

**Example:**
```json
{
  "subdomain": "humnoi"
}
```

**Response:**
```json
{
  "success": true,
  "count": 5,
  "event_types": [
    {
      "id": 1,
      "name": "General Checkup",
      "duration_minutes": 30,
      "description": "..."
    },
    ...
  ]
}
```

### create_booking

จองนัดหมายใหม่

**Parameters:**
- `subdomain` (string, required)
- `event_type_id` (integer, required)
- `date` (string, required): YYYY-MM-DD
- `time` (string, required): HH:MM
- `guest_name` (string, required)
- `guest_phone` (string, optional)
- `guest_email` (string, optional)
- `notes` (string, optional)

**Example:**
```json
{
  "subdomain": "humnoi",
  "event_type_id": 1,
  "date": "2025-11-25",
  "time": "10:00",
  "guest_name": "John Doe",
  "guest_phone": "0812345678"
}
```

**Response:**
```json
{
  "success": true,
  "booking_reference": "REF123456",
  "appointment_date": "2025-11-25",
  "appointment_time": "10:00",
  "message": "Booking created successfully"
}
```

### search_appointments

ค้นหานัดหมาย

**Parameters:**
- `subdomain` (string, required)
- `phone` (string, optional)
- `email` (string, optional)
- `booking_reference` (string, optional)

**Example:**
```json
{
  "subdomain": "humnoi",
  "phone": "0812345678"
}
```

**Response:**
```json
{
  "success": true,
  "count": 2,
  "appointments": [
    {
      "booking_reference": "REF123456",
      "date": "2025-11-25",
      "time": "10:00",
      "event_type_name": "General Checkup",
      "status": "confirmed"
    },
    ...
  ]
}
```

### cancel_booking

ยกเลิกนัดหมาย

**Parameters:**
- `subdomain` (string, required)
- `booking_reference` (string, required)
- `reason` (string, optional)

**Example:**
```json
{
  "subdomain": "humnoi",
  "booking_reference": "REF123456",
  "reason": "Schedule conflict"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Booking cancelled successfully"
}
```

### reschedule_booking

เลื่อนนัดหมาย

**Parameters:**
- `subdomain` (string, required)
- `booking_reference` (string, required)
- `new_date` (string, required): YYYY-MM-DD
- `new_time` (string, required): HH:MM
- `reason` (string, optional)

**Example:**
```json
{
  "subdomain": "humnoi",
  "booking_reference": "REF123456",
  "new_date": "2025-11-26",
  "new_time": "14:00"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Booking rescheduled successfully",
  "new_appointment_date": "2025-11-26",
  "new_appointment_time": "14:00"
}
```

## Troubleshooting

### MCP Server ไม่ทำงาน

1. ตรวจสอบ Claude Desktop logs:
   - **macOS**: `~/Library/Logs/Claude/mcp*.log`
   - **Windows**: `%APPDATA%\Claude\logs\mcp*.log`

2. ตรวจสอบ Python path:
   ```bash
   which python  # macOS/Linux
   where python  # Windows
   ```

3. ทดสอบรัน server โดยตรง:
   ```bash
   python server.py
   ```

### Tools ไม่ปรากฏใน Claude

1. ตรวจสอบ config file path ถูกต้อง
2. ตรวจสอบ absolute path ใน config
3. รีสตาร์ท Claude Desktop
4. ดู logs สำหรับ errors

### API Connection Failed

1. ตรวจสอบ FastAPI ทำงาน:
   ```bash
   curl http://localhost:8000/api/v1/tenants/humnoi/event-types
   ```

2. ตรวจสอบ FASTAPI_BASE_URL ใน .env

## Future Enhancements

- [ ] Add prompts (reusable templates)
- [ ] Add resources (API schemas)
- [ ] Add progress notifications
- [ ] Add caching
- [ ] Add error retry logic
- [ ] Add metrics/analytics

## License

MIT License

## Support

หากมีปัญหาหรือคำถาม:
- เปิด Issue บน GitHub
- ติดต่อทีมพัฒนา
