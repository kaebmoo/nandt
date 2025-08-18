# flask_app/run.py

import os
import sys
# เพิ่มโฟลเดอร์โปรเจกต์หลัก (hospital-booking) เข้าไปใน path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()
from app import create_app

# สร้าง app จาก factory
app = create_app()

if __name__ == '__main__':
    # รันบน port 5001 เพื่อไม่ให้ชนกับ FastAPI (8000)
    app.run(host='0.0.0.0', port=5001, debug=True)