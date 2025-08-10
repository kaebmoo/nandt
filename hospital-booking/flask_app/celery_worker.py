# flask_app/celery_worker.py

from .app import create_app

# สร้าง Flask app เพื่อให้ Celery เข้าถึง context และ config ได้
flask_app = create_app()

# ดึง Celery instance ที่สร้างและตั้งค่าไว้แล้วจาก app factory
celery_app = flask_app.extensions["celery"]