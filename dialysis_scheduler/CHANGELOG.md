# คู่มือสำหรับโปรแกรม Dialysis Scheduler

## app.py

โปรแกรม app.py เป็นแอปพลิเคชัน Flask หลักสำหรับระบบนัดหมายฟอกไต ทำหน้าที่กำหนด routes และจัดการการทำงานของแอปพลิเคชัน

### ฟังก์ชันหลัก

1. **การเชื่อมต่อ API**
   - เชื่อมต่อกับ TeamUp API ผ่านคลาส TeamupAPI
   - รองรับการตั้งค่าผ่านไฟล์ .env หรือผ่านหน้าเว็บ

2. **การจัดการนัดหมาย**
   - สร้างนัดหมายใหม่ (`create_appointment()`)
   - สร้างนัดหมายแบบเกิดซ้ำ (`recurring_appointments()`)
   - ดูรายการนัดหมาย (`appointments()`, `get_events()`)
   - อัปเดตสถานะนัดหมาย (`update_status()`)

3. **การจัดการปฏิทินย่อย**
   - แสดงรายการปฏิทินย่อย (`subcalendars()`)

4. **การนำเข้าข้อมูล**
   - นำเข้าข้อมูลนัดหมายจากไฟล์ CSV (`import_csv()`)

5. **ความปลอดภัยและระบบ**
   - ตรวจสอบการเชื่อมต่อ API ก่อนเข้าถึงหน้าต่างๆ (`is_api_connected()`, `check_api_connection()`)
   - ป้องกันการส่งฟอร์มซ้ำด้วยการใช้ tokens

### การใช้งาน

1. **หน้าหลัก** - `index()` - แสดงข้อมูลสรุปและสถานะการเชื่อมต่อ API
2. **ตั้งค่า API** - `setup()` - ตั้งค่าการเชื่อมต่อกับ TeamUp API
3. **จัดการนัดหมาย** - `appointments()` - แสดงหน้าจัดการนัดหมาย
4. **สร้างนัดหมายเกิดซ้ำ** - `recurring_appointments()` - สำหรับสร้างนัดหมายแบบเกิดซ้ำ
5. **อัปเดตสถานะ** - `update_status()` - สำหรับเปลี่ยนสถานะนัดหมาย
6. **นำเข้าข้อมูล** - `import_csv()` - นำเข้าข้อมูลนัดหมายจากไฟล์ CSV
7. **ออกจากระบบ** - `logout()` - ล้างการเชื่อมต่อ API

## config.py

โปรแกรม config.py เป็นไฟล์กำหนดค่าของระบบนัดหมายฟอกไต

### คุณสมบัติหลัก

1. **การโหลดค่าจากไฟล์ .env**
   - ใช้ dotenv สำหรับโหลดค่าจากไฟล์ .env
   - ตัวแปรสำคัญ: TEAMUP_API_KEY, CALENDAR_ID

2. **คลาส Config**
   - กำหนดค่าพื้นฐานสำหรับแอปพลิเคชัน Flask
   - รวมถึง SECRET_KEY, DEBUG, UPLOAD_FOLDER, MAX_CONTENT_LENGTH

3. **การสร้างโฟลเดอร์ที่จำเป็น**
   - มีเมธอด init_app() ที่สร้างโฟลเดอร์ uploads ถ้ายังไม่มี

### การใช้งาน

1. **ในแอปพลิเคชัน Flask**:
   ```python
   app.config.from_object(Config)
   Config.init_app()
   ```

2. **การเข้าถึงค่า API**:
   ```python
   from config import TEAMUP_API_KEY, CALENDAR_ID
   ```

## teamup_api.py

คลาส TeamupAPI ใน teamup_api.py เป็นส่วนที่จัดการการเชื่อมต่อกับ TeamUp Calendar API

### เมธอดหลัก

1. **การเชื่อมต่อและตรวจสอบ API**
   - `__init__(api_key, calendar_id)` - กำหนดค่าเริ่มต้น
   - `check_access()` - ตรวจสอบการเข้าถึง API

2. **การจัดการปฏิทินย่อย**
   - `get_subcalendars()` - ดึงรายการปฏิทินย่อย
   - `get_subcalendar_id(name)` - รับหรือสร้าง ID ปฏิทินย่อยจากชื่อ
   - `get_subcalendar_name_by_id(subcalendar_id)` - ค้นหาชื่อปฏิทินย่อยจาก ID

3. **การจัดการกิจกรรม**
   - `get_events(start_date, end_date, subcalendar_id)` - ดึงรายการกิจกรรม
   - `create_appointment(patient_data)` - สร้างนัดหมายใหม่
   - `create_recurring_appointment(patient_data, rrule)` - สร้างนัดหมายเกิดซ้ำตาม RFC 5545
   - `create_recurring_appointments_simple(patient_data, selected_days, weeks)` - สร้างนัดหมายเกิดซ้ำแบบง่าย
   - `update_appointment_status(event_id, status)` - อัปเดตสถานะนัดหมาย

4. **การนำเข้าข้อมูล**
   - `import_from_csv(file_path)` - นำเข้าข้อมูลจากไฟล์ CSV

5. **ฟังก์ชันช่วยเหลือ**
   - `generate_rrule(frequency, days, count, until)` - สร้าง RRULE string
   - `_format_datetime_to_timestamp(date_str, time_str)` - แปลงวันที่และเวลาเป็น timestamp
   - `_parse_datetime(date_str, time_str)` - แปลงวันที่และเวลาเป็น datetime object

### การใช้งานพื้นฐาน

1. **สร้าง Instance**:
   ```python
   teamup_api = TeamupAPI(api_key, calendar_id)
   success, message = teamup_api.check_access()
   ```

2. **สร้างนัดหมายใหม่**:
   ```python
   patient_data = {
       'title': 'ชื่อผู้ป่วย',
       'calendar_name': 'ชื่อปฏิทินย่อย',
       'start_date': '2023-05-01',
       'start_time': '10:00',
       'end_date': '2023-05-01',
       'end_time': '13:00',
       'location': 'สถานที่',
       'who': 'ผู้รับผิดชอบ',
       'description': 'รายละเอียดเพิ่มเติม'
   }
   success, result = teamup_api.create_appointment(patient_data)
   ```

3. **สร้างนัดหมายเกิดซ้ำ**:
   ```python
   selected_days = ['MO', 'WE', 'FR']  # จันทร์, พุธ, ศุกร์
   weeks = 4  # จำนวนสัปดาห์
   success, result = teamup_api.create_recurring_appointments_simple(patient_data, selected_days, weeks)
   ```

4. **อัปเดตสถานะนัดหมาย**:
   ```python
   event_id = '123456'
   status = 'มาตามนัด'  # หรือ 'ยกเลิก', 'ไม่มา'
   success, result = teamup_api.update_appointment_status(event_id, status)
   ```

5. **นำเข้าข้อมูลจาก CSV**:
   ```python
   results = teamup_api.import_from_csv('path/to/appointments.csv')
   print(f"นำเข้าสำเร็จ {results['success']} รายการ, ไม่สำเร็จ {results['failed']} รายการ")
   ```