# hospital-booking/flask_app/app/route.py

from flask import Blueprint, render_template, request, redirect, url_for
from .main import db_session, current_tenant
from .models import Appointment # สมมติว่ามี models อื่นๆ

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    # ถ้ามี subdomain อยู่แล้ว (เช่น hospital-a.localhost) ให้ไป dashboard
    if current_tenant:
        return redirect(url_for('main.dashboard'))
    
    # ถ้าไม่มี subdomain (เช่น localhost) ให้แสดงหน้า landing.html
    return render_template('landing.html')

@bp.route('/dashboard')
def dashboard():
    if not current_tenant:
        # ถ้าพยายามเข้า dashboard โดยไม่มี subdomain ให้กลับไปหน้าหลัก
        return redirect(url_for('main.index'))
    
    appointments = db_session.query(Appointment).order_by(Appointment.start_time.asc()).all()
    return render_template('dashboard.html', hospital=current_tenant, appointments=appointments)

# ไม่ต้องมี route /register ใน Flask แล้ว เพราะย้ายไป FastAPI
# ไม่ต้องมี route /webhook ใน Flask แล้ว ควรย้ายไป FastAPI เช่นกันเพื่อรวม API ไว้ที่เดียว