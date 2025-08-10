# flask_app/run.py

from app import create_app

# สร้าง app จาก factory
app = create_app()

if __name__ == '__main__':
    # รันบน port 5001 เพื่อไม่ให้ชนกับ FastAPI (8000)
    app.run(host='0.0.0.0', port=5001, debug=True)