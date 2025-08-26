# flask_app/app/holiday_routes.py

import os
import requests
from flask import Blueprint, render_template, request, flash, redirect, g, jsonify, url_for
from datetime import datetime

from .auth import login_required
from .core.tenant_manager import with_tenant
from .utils.url_helper import build_url_with_context

holiday_bp = Blueprint('holidays', __name__, url_prefix='/settings')

# --- Helper Functions ---

def get_fastapi_url():
    """Get FastAPI base URL from environment."""
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

def make_api_request(method, endpoint, json_data=None, params=None):
    """Helper to make API requests to FastAPI, relying on g.subdomain."""
    subdomain = getattr(g, 'subdomain', None)
    if not subdomain:
        return None, "ไม่พบข้อมูล tenant"
    
    url = f"{get_fastapi_url()}/api/v1/tenants/{subdomain}{endpoint}"
    try:
        response = requests.request(method, url, json=json_data, params=params, timeout=15)
        
        # สำหรับ DELETE ที่อาจจะไม่มี content ตอบกลับมา
        if response.status_code == 204:
            return {}, None
            
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        error_detail = "เกิดข้อผิดพลาดในการเชื่อมต่อ"
        try:
            error_detail = e.response.json().get('detail', str(e))
        except (AttributeError, ValueError, TypeError):
            pass
        return None, error_detail

# --- Routes ---

@holiday_bp.route('/holidays')
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def holiday_settings():
    """หน้าหลักสำหรับจัดการวันหยุด"""
    year = request.args.get('year', datetime.now().year, type=int)
    
    holidays_data, error = make_api_request('GET', '/holidays', params={'year': year})
    
    if error:
        flash(f"ไม่สามารถโหลดข้อมูลวันหยุดได้: {error}", "error")
        holidays_list = []
    else:
        holidays_list = holidays_data if holidays_data else []
        # แปลง date string ที่ได้จาก API กลับเป็น date object
        for holiday in holidays_list:
            if isinstance(holiday.get('date'), str):
                try:
                    holiday['date'] = datetime.strptime(holiday['date'], '%Y-%m-%d').date()
                except ValueError:
                    holiday['date'] = None 
        
    return render_template('settings/holidays.html', 
                           holidays=holidays_list, 
                           selected_year=year,
                           current_year=datetime.now().year)

@holiday_bp.route('/holidays/sync', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def sync_holidays():
    """Manual sync button action - now just passes year to FastAPI"""
    year = request.form.get('year', datetime.now().year, type=int)
    
    # ส่งแค่ปี ให้ FastAPI fetch เอง
    payload = {
        "year": year,
        "holidays": []  # ส่งว่างไป FastAPI จะ fetch เอง
    }
    
    result, error = make_api_request('POST', '/holidays/sync', json_data=payload)
    
    if error:
        flash(f"เกิดข้อผิดพลาด: {error}", "error")
    else:
        flash(result.get('message', "นำเข้าวันหยุดสำเร็จ!"), "success")
        
    return redirect(build_url_with_context('holidays.holiday_settings', year=year))

@holiday_bp.route('/holidays/add', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def add_custom_holiday():
    """เพิ่มวันหยุดที่กำหนดเอง"""
    payload = {
        "date": request.form.get('date'),
        "name": request.form.get('name'),
        "description": request.form.get('description'),
        "source": "manual"
    }
    _, error = make_api_request('POST', '/holidays', json_data=payload)
    if error:
        flash(f"ไม่สามารถเพิ่มวันหยุดได้: {error}", "error")
    else:
        flash("เพิ่มวันหยุดเรียบร้อยแล้ว", "success")
    return redirect(build_url_with_context('holidays.holiday_settings'))

@holiday_bp.route('/holidays/delete/<int:holiday_id>', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def delete_holiday(holiday_id):
    """ลบวันหยุด"""
    _, error = make_api_request('DELETE', f'/holidays/{holiday_id}')
    if error:
        flash(f"ไม่สามารถลบวันหยุดได้: {error}", "error")
    else:
        flash("ลบวันหยุดเรียบร้อยแล้ว", "success")
    return redirect(build_url_with_context('holidays.holiday_settings'))

@holiday_bp.route('/holidays/toggle/<int:holiday_id>', methods=['POST'])
@login_required
@with_tenant(require_access=True)
def toggle_holiday(holiday_id):
    """AJAX endpoint สำหรับเปิด/ปิดวันหยุด"""
    is_active = request.form.get('is_active', 'false').lower() == 'true'
    payload = {"is_active": is_active}
    
    result, error = make_api_request('PATCH', f'/holidays/{holiday_id}', json_data=payload)
    if error:
        return jsonify({"error": error}), 400
    
    return jsonify({"success": True, "data": result})