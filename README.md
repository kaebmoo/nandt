# nandt

Dialysis Scheduler

# โครงสร้างไฟล์โปรเจค Dialysis Scheduler

```
dialysis_scheduler/
├── app.py                  # ไฟล์หลักของแอปพลิเคชัน (อัปเดตแล้ว)
├── config.py               # การตั้งค่าต่างๆ
├── teamup_api.py           # โมดูลสำหรับเชื่อมต่อกับ TeamUp API (อัปเดตแล้ว)
├── forms.py                # ฟอร์มสำหรับการสร้างนัดหมาย (สร้างใหม่)
├── requirements.txt        # รายการแพ็คเกจที่ต้องติดตั้ง
├── .env                    # ไฟล์เก็บ API keys (สร้างอัตโนมัติ)
├── .gitignore              # ไฟล์ระบุสิ่งที่ไม่ต้อง commit
├── README.md               # คู่มือการใช้งาน
├── static/                 # โฟลเดอร์สำหรับไฟล์ CSS, JavaScript, และรูปภาพ
│   ├── css/
│   │   └── style.css       # ไฟล์ CSS หลัก (เพิ่ม/อัปเดต)
│   ├── js/
│   │   └── script.js       # ไฟล์ JavaScript หลัก (อัปเดตแล้ว)
│   └── img/                # รูปภาพต่างๆ
├── templates/              # โฟลเดอร์สำหรับเทมเพลต HTML
│   ├── base.html           # เทมเพลตหลัก (อัปเดตแล้ว)
│   ├── index.html          # หน้าแรก
│   ├── setup.html          # หน้าตั้งค่า API
│   ├── appointments.html   # หน้าจัดการนัดหมาย (อัปเดตแล้ว)
│   ├── recurring_appointments.html  # หน้าสร้างนัดหมายเกิดซ้ำ (สร้างใหม่)
│   ├── update_status.html  # หน้าอัปเดตสถานะนัดหมาย
│   ├── subcalendars.html   # หน้าแสดงรายการปฏิทินย่อย
│   └── import.html         # หน้านำเข้าข้อมูลจาก CSV
└── uploads/                # โฟลเดอร์สำหรับไฟล์อัปโหลด (สร้างอัตโนมัติ)
```

## คำอธิบายไฟล์สำคัญ

### ไฟล์หลัก (Backend)
- **`app.py`** - ไฟล์หลักของ Flask application รวมทุก routes และ logic
- **`teamup_api.py`** - โมดูลสำหรับเชื่อมต่อกับ TeamUp Calendar API
- **`forms.py`** - ฟอร์มสำหรับการสร้างนัดหมายด้วย WTForms
- **`config.py`** - การตั้งค่าของแอปพลิเคชัน

### ไฟล์กำหนดค่า
- **`.env`** - เก็บ API keys และการตั้งค่าที่ละเอียดอ่อน
- **`requirements.txt`** - รายการ Python packages ที่ต้องติดตั้ง
- **`.gitignore`** - ระบุไฟล์ที่ไม่ต้อง commit ลง Git

### Frontend (Templates & Static)
- **`templates/`** - เทมเพลต HTML ทั้งหมด
- **`static/css/style.css`** - สไตล์ CSS หลัก
- **`static/js/script.js`** - JavaScript สำหรับ interactive features

### โฟลเดอร์อัตโนมัติ
- **`uploads/`** - เก็บไฟล์ CSV ที่อัปโหลดชั่วคราว
- **`__pycache__/`** - Python cache files (ไม่แสดงในแผนภาพ)

## ไฟล์ที่อัปเดตล่าสุด 

### อัปเดตแล้ว:
-  `app.py` - เพิ่มฟีเจอร์ recurring appointments
-  `teamup_api.py` - รองรับ RRULE และ recurring events
-  `forms.py` - ฟอร์มสำหรับนัดหมายแบบเกิดซ้ำ
-  `templates/appointments.html` - UI สำหรับจัดการนัดหมาย
-  `templates/base.html` - เพิ่ม navigation และ dependencies
-  `static/js/script.js` - JavaScript สำหรับ AJAX และ UI interactions
-  `static/css/style.css` - สไตล์สำหรับ appointment cards และ UI

### สร้างใหม่:
- `forms.py` - WTForms สำหรับ validation
- `templates/recurring_appointments.html` - หน้าสร้างนัดหมายเกิดซ้ำ

