# nandt

Dialysis Scheduler

dialysis_scheduler/
├── app.py                  # ไฟล์หลักของแอปพลิเคชัน
├── config.py               # การตั้งค่าต่างๆ
├── teamup_api.py           # โมดูลสำหรับเชื่อมต่อกับ TeamUp API
├── requirements.txt        # รายการแพ็คเกจที่ต้องติดตั้ง
├── static/                 # โฟลเดอร์สำหรับไฟล์ CSS, JavaScript, และรูปภาพ
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── script.js
│   └── img/
└── templates/              # โฟลเดอร์สำหรับเทมเพลต HTML
    ├── base.html           # เทมเพลตหลัก
    ├── index.html          # หน้าแรก
    ├── setup.html          # หน้าตั้งค่า API
    ├── appointments.html   # หน้าจัดการนัดหมาย
    └── import.html         # หน้านำเข้าข้อมูล