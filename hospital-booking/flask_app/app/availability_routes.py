# flask_app/app/availability_routes.py

import os
import requests
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort, g
from .auth import login_required, check_tenant_access
from .core.tenant_manager import with_tenant  # import decorator
from .forms import (
    AvailabilityTemplateForm, QuickSetupForm,
    populate_availability_form_from_api_data, create_default_template_form
)
from .auth import get_current_user 
from .core.tenant_manager import TenantManager
from .utils.url_helper import build_url_with_context


# สร้าง Blueprint สำหรับ availability
availability_bp = Blueprint('availability', __name__, url_prefix='/settings')

# API helper functions
def get_fastapi_url():
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

def make_api_request(method, endpoint, data=None, params=None):
    """Helper function สำหรับ API calls ไป FastAPI"""
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    if not subdomain:
        return None, "ไม่พบข้อมูล tenant"
    
    url = f"{get_fastapi_url()}/api/v1/tenants/{subdomain}{endpoint}"
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, params=params, timeout=10)
        elif method.upper() == 'POST':
            response = requests.post(url, json=data, timeout=10)
        elif method.upper() == 'PUT':
            response = requests.put(url, json=data, timeout=10)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, timeout=10)
        else:
            return None, f"Unsupported method: {method}"
        
        if response.ok:
            return response.json(), None
        else:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            return None, error_data.get('detail', f'API Error: {response.status_code}')
            
    except requests.exceptions.RequestException as e:
        return None, f"การเชื่อมต่อ API ล้มเหลว: {str(e)}"
    except Exception as e:
        return None, f"เกิดข้อผิดพลาด: {str(e)}"

# ===== MAIN AVAILABILITY PAGE =====
@availability_bp.route('/availability')
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def availability_settings():
    """หน้าหลักแสดงรายการ availability templates"""
    current_user = get_current_user()
    subdomain = g.subdomain 
    # tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))
    
    # if not current_user or not check_tenant_access(subdomain):
    #     flash('ไม่สามารถเข้าถึงได้', 'error')
    #     return redirect(build_url_with_context('main.index'))

    
    # ดึงข้อมูล templates จาก endpoint ใหม่
    templates_data, error = make_api_request('GET', '/availability/templates')
    
    if error:
        flash(f'เกิดข้อผิดพลาดในการโหลดเทมเพลต: {error}', 'error')
        templates = []
    else:
        templates = templates_data.get('templates', [])
        
        # ดึง schedule details สำหรับแต่ละ template
        for template in templates:
            detail_data, _ = make_api_request('GET', f'/availability/template/{template["id"]}/details')
            if detail_data:
                template['schedule'] = detail_data.get('schedule', {})
    
    # เลือก template
    selected_template_id = request.args.get('selected_template', type=int)
    selected_template = None
    
    if selected_template_id:
        selected_template = next((t for t in templates if t['id'] == selected_template_id), None)
    elif templates:
        selected_template = templates[0]
    
    # ดึง date overrides
    template_overrides = []
    if selected_template:
        overrides_data, _ = make_api_request('GET', '/date-overrides', params={'template_id': selected_template['id']})
        if overrides_data:
            template_overrides = overrides_data.get('date_overrides', [])
    
    return render_template('settings/availability/index.html',
                         current_user=current_user,
                         templates=templates,
                         selected_template=selected_template,
                         template_overrides=template_overrides,
                         subdomain=subdomain)

# ===== CREATE TEMPLATE =====
@availability_bp.route('/availability/template/new', methods=['GET', 'POST'])
@login_required
def create_template():
    """สร้าง availability template ใหม่"""

    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    
    # Handle quick setup
    quick_form = QuickSetupForm()
    if request.method == 'POST' and 'quick_setup' in request.form:
        if quick_form.validate_on_submit() and quick_form.preset.data != 'custom':
            preset_data = quick_form.get_preset_schedule()
            if preset_data:
                # ส่งข้อมูล preset ไป API
                preset_data['timezone'] = 'Asia/Bangkok'
                api_data, error = make_api_request('POST', '/availability', preset_data)
                
                if error:
                    flash(f'เกิดข้อผิดพลาดในการสร้างเทมเพลต: {error}', 'error')
                else:
                    flash('สร้างเทมเพลตจาก preset เรียบร้อยแล้ว!', 'success')
                    return redirect(build_url_with_context('availability.availability_settings'))
    
    # Handle manual form
    if request.method == 'GET' or (request.method == 'POST' and 'quick_setup' not in request.form):
        form = AvailabilityTemplateForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            # ส่งข้อมูลไป API
            api_data, error = make_api_request('POST', '/availability', form.get_schedule_data())
            
            if error:
                flash(f'เกิดข้อผิดพลาดในการสร้างเทมเพลต: {error}', 'error')
            else:
                flash('สร้างเทมเพลตเรียบร้อยแล้ว!', 'success')
                template_id = api_data.get('template_id') if api_data else None
                if template_id:
                    return redirect(build_url_with_context('availability.availability_settings', selected_template=template_id))
                else:
                    return redirect(build_url_with_context('availability.availability_settings'))
                
        
        # ถ้าเป็น GET หรือ validation fail
        if request.method == 'GET':
            form = create_default_template_form()
    
    return render_template('settings/availability/form.html',
                         form=form,
                         quick_form=quick_form,
                         current_user=current_user,
                         action='create',
                         page_title='สร้างเทมเพลตใหม่')

# ===== EDIT TEMPLATE (FINAL CORRECTED VERSION) =====
@availability_bp.route('/availability/template/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    """แก้ไข availability template (ฉบับแก้ไขสมบูรณ์)"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    # 1. ดึงข้อมูลต้นฉบับของ Template จาก API
    template_details, error = make_api_request('GET', f'/availability/template/{template_id}/details')
    if error or not template_details:
        flash(f'ไม่สามารถโหลดข้อมูลเทมเพลตได้: {error}', 'error')
        return redirect(build_url_with_context('availability.availability_settings'))

    # 2. สร้าง Instance ของ Form
    form = AvailabilityTemplateForm(request.form)

    # 3. จัดการเมื่อมีการส่งฟอร์มและข้อมูลถูกต้อง
    if form.validate_on_submit():
        schedule_data = form.get_schedule_data()
        api_data, error = make_api_request('PUT', f'/availability/templates/{template_id}', schedule_data)

        if not error:
            flash('แก้ไขเทมเพลตเรียบร้อยแล้ว!', 'success')
            return redirect(build_url_with_context('availability.availability_settings', selected_template=template_id))
        else:
            flash(f'เกิดข้อผิดพลาดในการบันทึก: {error}', 'error')

    # 4. เติมข้อมูลลงในฟอร์ม (สำหรับ GET request หรือเมื่อ POST ล้มเหลว)
    
    # ถ้าไม่ใช่การ submit (คือเป็น GET request) ให้ดึงค่าจาก API มาใส่
    if not form.is_submitted():
        form.name.data = template_details.get('name')
        form.description.data = template_details.get('description')
        form.timezone.data = template_details.get('timezone', 'Asia/Bangkok')

    # เติมข้อมูล "ช่องเวลา" (slots) จาก API เสมอ
    day_fields = [form.sunday, form.monday, form.tuesday, form.wednesday, form.thursday, form.friday, form.saturday]
    schedule = template_details.get('schedule', {})
    from datetime import datetime

    for day_index, day_field in enumerate(day_fields):
        # ล้าง slots เก่าทิ้งก่อน
        while day_field.slots.entries:
            day_field.slots.pop_entry()
            
        day_str = str(day_index)
        # เติมข้อมูลจาก API ถ้ามี
        if day_str in schedule:
            if not form.is_submitted():
                day_field.enabled.data = True

            for slot_data in schedule[day_str]:
                start_time = datetime.strptime(slot_data['start'], '%H:%M').time()
                end_time = datetime.strptime(slot_data['end'], '%H:%M').time()
                day_field.slots.append_entry({'start_time': start_time, 'end_time': end_time})
        else:
            if not form.is_submitted():
                day_field.enabled.data = False
        
        # ตรวจสอบให้แน่ใจว่าทุกวันมีอย่างน้อย 1 slot สำหรับ UI
        if not day_field.slots.entries:
            day_field.slots.append_entry()

    # 5. ดึงข้อมูล Date Overrides
    overrides_data, _ = make_api_request('GET', '/date-overrides', params={'template_id': template_id})
    template_overrides = overrides_data.get('date_overrides', []) if overrides_data else []

    # 6. Render หน้าเว็บ
    return render_template('settings/availability/form.html',
                         form=form,
                         current_user=current_user,
                         action='edit',
                         template_id=template_id,
                         template_overrides=template_overrides,
                         page_title=f'แก้ไขเทมเพลต: {template_details["name"]}')

# ===== DELETE TEMPLATE =====
@availability_bp.route('/availability/template/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    """ลบ availability template"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    
    # ส่งคำขอลบไป API
    api_data, error = make_api_request('DELETE', f'/availability/templates/{template_id}')
    
    if error:
        flash(f'เกิดข้อผิดพลาดในการลบ: {error}', 'error')
    else:
        flash(api_data.get('message', 'ลบเทมเพลตเรียบร้อยแล้ว'), 'success')
        
        # แสดง event types ที่ถูกย้าย (ถ้ามี)
        if 'moved_events' in api_data and api_data['moved_events']:
            moved_events = ', '.join(api_data['moved_events'])
            flash(f'Event Types ที่ถูกย้ายไปใช้เทมเพลตเริ่มต้น: {moved_events}', 'info')
    
    return redirect(build_url_with_context('availability.availability_settings'))

# ===== DATE OVERRIDES =====
@availability_bp.route('/availability/date-override/new', methods=['POST'])
@login_required
def create_date_override():
    """สร้าง date override ใหม่"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    
    # รับข้อมูลจาก form
    date_str = request.form.get('date')
    override_type = request.form.get('override_type')
    custom_start_time = request.form.get('custom_start_time')
    custom_end_time = request.form.get('custom_end_time')
    reason = request.form.get('reason', '')
    template_id = request.form.get('template_id')
    scope = request.form.get('scope', 'template')
    
    # Date input type="date" จะส่งมาเป็น yyyy-mm-dd อยู่แล้ว
    # ไม่ต้องแปลงอีก
    if not date_str:
        flash('กรุณาเลือกวันที่', 'error')
        return redirect(request.referrer or build_url_with_context('availability.availability_settings'))
    
    # สร้าง data สำหรับส่งไป API
    api_data = {
        'date': date_str,
        'is_unavailable': override_type == 'unavailable',
        'reason': reason,
        'template_scope': scope
    }
    
    if override_type == 'custom' and custom_start_time and custom_end_time:
        api_data['custom_start_time'] = custom_start_time
        api_data['custom_end_time'] = custom_end_time
    
    if template_id:
        api_data['template_id'] = int(template_id)
    
    # ส่งข้อมูลไป API
    result, error = make_api_request('POST', '/date-overrides', api_data)
        
    if error:
        flash(f'เกิดข้อผิดพลาดในการเพิ่มวันพิเศษ: {error}', 'error')
    else:
        flash('เพิ่มวันพิเศษเรียบร้อยแล้ว!', 'success')
    
    return redirect(request.referrer or build_url_with_context('availability.availability_settings'))

@availability_bp.route('/availability/date-override/<int:override_id>/delete', methods=['POST'])
@login_required
def delete_date_override(override_id):
    """ลบ date override"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    
    # ส่งคำขอลบไป API
    api_data, error = make_api_request('DELETE', f'/date-overrides/{override_id}')
    
    if error:
        flash(f'เกิดข้อผิดพลาดในการลบ: {error}', 'error')
    else:
        flash('ลบวันพิเศษเรียบร้อยแล้ว!', 'success')
    
    return redirect(request.referrer or build_url_with_context('availability.availability_settings'))

# ===== AJAX API ENDPOINTS =====
@availability_bp.route('/api/template/<int:template_id>/overrides')
@login_required
def get_template_overrides(template_id):
    """AJAX endpoint สำหรับดึง date overrides ของ template"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # ดึงข้อมูล date overrides สำหรับ template นี้
    overrides_data, error = make_api_request('GET', '/date-overrides', params={'template_id': template_id})
    
    if error:
        return jsonify({'error': error}), 500
    
    # กรองเฉพาะของ template นี้
    template_overrides = [o for o in overrides_data.get('date_overrides', []) 
                         if o.get('template_id') == template_id]
    
    return jsonify({
        'date_overrides': template_overrides,
        'template_id': template_id
    })

@availability_bp.route('/api/template/<int:template_id>/details')
@login_required  
def get_template_details(template_id):
    """AJAX endpoint สำหรับดึงรายละเอียด template"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # ใช้ endpoint ใหม่โดยตรง
    template_data, error = make_api_request('GET', f'/availability/template/{template_id}/details')
    
    if error:
        return jsonify({'error': error}), 500
    
    if not template_data:
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify(template_data)

# ===== UTILITY ROUTES =====
@availability_bp.route('/api/quick-setup', methods=['POST'])
@login_required
def quick_setup():
    """AJAX endpoint สำหรับ quick setup"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        return jsonify({'error': 'Unauthorized'}), 401
    
    form = QuickSetupForm()
    
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid form data', 'errors': form.errors}), 400
    
    if form.preset.data == 'custom':
        return jsonify({'message': 'Custom setup selected'}), 200
    
    # ดึงข้อมูล preset
    preset_data = form.get_preset_schedule()
    if not preset_data:
        return jsonify({'error': 'Invalid preset'}), 400
    
    preset_data['timezone'] = 'Asia/Bangkok'
    
    # ส่งไป API
    api_data, error = make_api_request('POST', '/availability', preset_data)
    
    if error:
        return jsonify({'error': error}), 500
    
    return jsonify({
        'message': 'สร้างเทมเพลตจาก preset เรียบร้อยแล้ว',
        'template_name': preset_data['name']
    })

@availability_bp.route('/api/validate-template-name')
@login_required
def validate_template_name():
    """AJAX endpoint สำหรับตรวจสอบชื่อ template ซ้ำ"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()
    
    if not current_user or not check_tenant_access(subdomain):
        return jsonify({'error': 'Unauthorized'}), 401
    
    name = request.args.get('name', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)  # สำหรับการแก้ไข
    
    if not name:
        return jsonify({'valid': False, 'message': 'กรุณาใส่ชื่อเทมเพลต'})
    
    # ดึงรายการ templates ที่มีอยู่
    templates_data, error = make_api_request('GET', '/availability/templates')
    if error:
        return jsonify({'valid': False, 'message': 'ไม่สามารถตรวจสอบได้'})
    
    templates = templates_data.get('templates', [])
    
    # ตรวจสอบชื่อซ้ำ
    for template in templates:
        if template['name'].lower() == name.lower():
            if exclude_id is None or template['id'] != exclude_id:
                return jsonify({'valid': False, 'message': 'ชื่อเทมเพลตนี้มีอยู่แล้ว'})
    
    return jsonify({'valid': True, 'message': 'ชื่อเทมเพลตใช้ได้'})

# ===== ERROR HANDLERS =====
@availability_bp.errorhandler(404)
def not_found_error(error):
    flash('ไม่พบหน้าที่ต้องการ', 'error')
    return redirect(build_url_with_context('availability.availability_settings'))

@availability_bp.errorhandler(500)
def internal_error(error):
    flash('เกิดข้อผิดพลาดภายในระบบ', 'error')
    return redirect(build_url_with_context('availability.availability_settings'))
