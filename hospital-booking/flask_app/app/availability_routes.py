# flask_app/app/availability_routes.py

import os
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort, g, make_response
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
        elif method.upper() == 'PATCH':
            response = requests.patch(url, json=data, timeout=10)
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


def redirect_to_template_settings(template_id):
    return redirect(build_url_with_context('availability.availability_settings', selected_template=template_id))

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
                template['providers_detail'] = detail_data.get('providers', [])
                template['provider_schedules_detail'] = detail_data.get('provider_schedules', [])
                template['resource_capacities_detail'] = detail_data.get('resource_capacities', [])
                template['template_type'] = detail_data.get('template_type', template.get('template_type'))
                template['max_concurrent_slots'] = detail_data.get('max_concurrent_slots', template.get('max_concurrent_slots'))
                template['requires_provider_assignment'] = detail_data.get('requires_provider_assignment', template.get('requires_provider_assignment', True))
                template['timezone'] = detail_data.get('timezone', template.get('timezone'))
    
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

    # ดึงรายการผู้ให้บริการทั้งหมดสำหรับการจัดการ assignment
    providers_data, providers_error = make_api_request('GET', '/providers')
    provider_options = []
    if providers_error:
        flash(f'เกิดข้อผิดพลาดในการโหลดรายชื่อผู้ให้บริการ: {providers_error}', 'warning')
    elif providers_data:
        provider_options = providers_data.get('providers', [])
    
    # สร้าง response และเพิ่ม cache control headers
    response = make_response(render_template('settings/availability/index.html',
                                            current_user=current_user,
                                            templates=templates,
                                            selected_template=selected_template,
                                            template_overrides=template_overrides,
                                            provider_options=provider_options,
                                            subdomain=subdomain))
    
    # ป้องกัน browser cache เพื่อให้ข้อมูลอัปเดตทันที
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

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
    
    # Initialize form first to avoid UnboundLocalError
    form = AvailabilityTemplateForm()
    quick_form = QuickSetupForm()
    
    # Handle quick setup
    if request.method == 'POST' and 'quick_setup' in request.form:
        if quick_form.validate_on_submit() and quick_form.preset.data != 'custom':
            preset_data = quick_form.get_preset_schedule()
            if preset_data:
                # ส่งข้อมูล preset ไป API
                preset_data['timezone'] = 'Asia/Bangkok'
                api_data, error = make_api_request('POST', '/availability', preset_data)
                
                if error:
                    flash(f'เกิดข้อผิดพลาดในการสร้างเทมเพลต: {error}', 'error')
                    # แม้ error ก็ให้ใช้ default form
                    form = create_default_template_form()
                else:
                    flash('สร้างเทมเพลตจาก preset เรียบร้อยแล้ว!', 'success')
                    return redirect(build_url_with_context('availability.availability_settings'))
    
    # Handle manual form
    elif request.method == 'POST' and 'quick_setup' not in request.form:
        if form.validate_on_submit():
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
    
    # For GET request, initialize with default values
    if request.method == 'GET':
        form = create_default_template_form()
    
    return render_template('settings/availability/form.html',
                         form=form,
                         quick_form=quick_form,
                         current_user=current_user,
                         action='create',
                         template_overrides=[],
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
        form.template_type.data = template_details.get('template_type', 'dedicated')
        form.max_concurrent_slots.data = template_details.get('max_concurrent_slots', 1)
        form.requires_provider_assignment.data = template_details.get('requires_provider_assignment', True)

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
        # จัดการ error cases ต่างๆ ให้ดีขึ้น
        error_str = str(error).lower()
        if "404" in error_str or "not found" in error_str:
            flash('เทมเพลตนี้ถูกลบไปแล้ว หรือไม่มีอยู่ในระบบ', 'warning')
        elif "400" in error_str or "bad request" in error_str:
            flash('ไม่สามารถลบเทมเพลตนี้ได้ เนื่องจากมีการใช้งานอยู่', 'error')
        elif "connection" in error_str or "timeout" in error_str:
            flash('ไม่สามารถเชื่อมต่อกับระบบได้ กรุณาลองใหม่อีกครั้ง', 'error')
        else:
            flash(f'เกิดข้อผิดพลาดในการลบ: {error}', 'error')
    else:
        flash(api_data.get('message', 'ลบเทมเพลตเรียบร้อยแล้ว'), 'success')
        
        # แสดง event types ที่ถูกย้าย (ถ้ามี)
        if 'moved_events' in api_data and api_data['moved_events']:
            moved_events = ', '.join(api_data['moved_events'])
            flash(f'Event Types ที่ถูกย้ายไปใช้เทมเพลตเริ่มต้น: {moved_events}', 'info')
    
    # Redirect โดยไม่ส่ง selected_template parameter เพื่อป้องกันการแสดง template ที่ถูกลบ
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
    
    if override_type == 'custom':
        if not custom_start_time or not custom_end_time:
            flash('กรุณาระบุเวลาเริ่มและเวลาสิ้นสุดสำหรับเวลาพิเศษ', 'error')
            return redirect(request.referrer or build_url_with_context('availability.availability_settings'))
        try:
            start_dt = datetime.strptime(custom_start_time, '%H:%M')
            end_dt = datetime.strptime(custom_end_time, '%H:%M')
        except ValueError:
            flash('รูปแบบเวลาไม่ถูกต้อง', 'error')
            return redirect(request.referrer or build_url_with_context('availability.availability_settings'))
        if start_dt >= end_dt:
            flash('เวลาสิ้นสุดต้องมากกว่าเวลาเริ่ม', 'error')
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
        flash('เพิ่มวันพิเศษเรียบร้อยแล้ว (ระบบบันทึกทันที)', 'success')
    
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


# ===== TEMPLATE PROVIDER ASSIGNMENTS =====

@availability_bp.route('/availability/template/<int:template_id>/providers/add', methods=['POST'])
@login_required
def add_template_provider(template_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    try:
        provider_id = int(request.form.get('provider_id', ''))
    except (TypeError, ValueError):
        flash('กรุณาเลือกผู้ให้บริการ', 'error')
        return redirect_to_template_settings(template_id)

    is_primary = request.form.get('is_primary') == 'on'
    can_auto_assign = request.form.get('can_auto_assign') != 'off' and request.form.get('can_auto_assign') is not None
    priority_value = request.form.get('priority', '0')
    try:
        priority = int(priority_value)
    except ValueError:
        priority = 0

    payload = {
        'provider_id': provider_id,
        'is_primary': is_primary,
        'can_auto_assign': can_auto_assign,
        'priority': priority
    }

    _, error = make_api_request('POST', f'/availability/templates/{template_id}/providers', payload)

    if error:
        flash(f'ไม่สามารถเพิ่มผู้ให้บริการได้: {error}', 'error')
    else:
        flash('เพิ่มผู้ให้บริการให้เทมเพลตเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/providers/add-batch', methods=['POST'])
@login_required
def add_template_providers_batch(template_id):
    """เพิ่มผู้ให้บริการหลายคนพร้อมกันในเทมเพลต"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    # รับ list ของ provider_ids ที่เลือก
    provider_ids = request.form.getlist('provider_ids')

    if not provider_ids:
        flash('กรุณาเลือกผู้ให้บริการอย่างน้อย 1 คน', 'error')
        return redirect_to_template_settings(template_id)

    # รับค่า default settings
    default_is_primary = request.form.get('default_is_primary') == 'on'
    default_can_auto_assign = request.form.get('default_can_auto_assign') == 'on'
    default_priority_value = request.form.get('default_priority', '0')
    auto_create_schedule = request.form.get('auto_create_schedule') == 'on'

    try:
        default_priority = int(default_priority_value)
    except ValueError:
        default_priority = 0

    # ดึงข้อมูล template เพื่อใช้สร้าง schedule
    template_data = None
    if auto_create_schedule:
        template_detail, _ = make_api_request('GET', f'/availability/template/{template_id}/details')
        if template_detail:
            template_data = template_detail

    # เก็บผลลัพธ์
    success_count = 0
    schedule_created_count = 0
    errors = []
    schedule_errors = []
    added_provider_ids = []

    # วนลูปเพิ่มผู้ให้บริการทีละคน
    for provider_id_str in provider_ids:
        try:
            provider_id = int(provider_id_str)
            payload = {
                'provider_id': provider_id,
                'is_primary': default_is_primary,
                'can_auto_assign': default_can_auto_assign,
                'priority': default_priority
            }

            _, error = make_api_request('POST', f'/availability/templates/{template_id}/providers', payload)

            if error:
                errors.append(f'Provider ID {provider_id}: {error}')
            else:
                success_count += 1
                added_provider_ids.append(provider_id)

        except (TypeError, ValueError):
            errors.append(f'Invalid provider ID: {provider_id_str}')

    # สร้าง schedule อัตโนมัติ ถ้าเลือก
    if auto_create_schedule and added_provider_ids and template_data:
        from datetime import date

        # ดึงวันทำงานจาก template schedule
        schedule_map = template_data.get('schedule', {})
        days_of_week = sorted([int(day) for day in schedule_map.keys() if schedule_map[day]])

        if days_of_week:
            for provider_id in added_provider_ids:
                try:
                    schedule_payload = {
                        'provider_id': provider_id,
                        'effective_date': date.today().isoformat(),
                        'end_date': None,
                        'days_of_week': days_of_week,
                        'custom_start_time': None,  # ใช้ตาม template
                        'custom_end_time': None,
                        'schedule_type': 'regular',
                        'notes': 'สร้างอัตโนมัติจากการเพิ่มผู้ให้บริการ'
                    }

                    _, schedule_error = make_api_request('POST', f'/availability/templates/{template_id}/schedules', schedule_payload)

                    if schedule_error:
                        schedule_errors.append(f'Provider ID {provider_id}: {schedule_error}')
                    else:
                        schedule_created_count += 1

                except Exception as e:
                    schedule_errors.append(f'Provider ID {provider_id}: {str(e)}')

    # แสดง flash message สรุปผลลัพธ์
    if success_count > 0:
        flash(f'เพิ่มผู้ให้บริการสำเร็จ {success_count} คน', 'success')

    if schedule_created_count > 0:
        flash(f'สร้างตารางทำงานอัตโนมัติสำเร็จ {schedule_created_count} คน', 'success')

    if errors:
        # แสดงเฉพาะ 3 error แรก เพื่อไม่ให้ message ยาวเกินไป
        for error in errors[:3]:
            flash(error, 'error')
        if len(errors) > 3:
            flash(f'และมี error อีก {len(errors) - 3} รายการ', 'warning')

    if schedule_errors:
        for error in schedule_errors[:2]:
            flash(f'ตาราง: {error}', 'warning')
        if len(schedule_errors) > 2:
            flash(f'และมี error ในการสร้างตารางอีก {len(schedule_errors) - 2} รายการ', 'warning')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/providers/<int:provider_id>/update', methods=['POST'])
@login_required
def update_template_provider(template_id, provider_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    payload = {}

    if 'is_primary' in request.form:
        payload['is_primary'] = 'on' in request.form.getlist('is_primary')
    if 'can_auto_assign' in request.form:
        payload['can_auto_assign'] = 'on' in request.form.getlist('can_auto_assign')
    if 'priority' in request.form:
        try:
            payload['priority'] = int(request.form.get('priority') or 0)
        except ValueError:
            flash('ลำดับความสำคัญต้องเป็นตัวเลข', 'error')
            return redirect_to_template_settings(template_id)

    if not payload:
        flash('ไม่มีข้อมูลสำหรับอัปเดต', 'warning')
        return redirect_to_template_settings(template_id)

    _, error = make_api_request('PATCH', f'/availability/templates/{template_id}/providers/{provider_id}', payload)

    if error:
        flash(f'ไม่สามารถอัปเดตข้อมูลผู้ให้บริการได้: {error}', 'error')
    else:
        flash('อัปเดตข้อมูลผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/providers/<int:provider_id>/delete', methods=['POST'])
@login_required
def delete_template_provider(template_id, provider_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    _, error = make_api_request('DELETE', f'/availability/templates/{template_id}/providers/{provider_id}')

    if error:
        flash(f'ไม่สามารถนำผู้ให้บริการออกได้: {error}', 'error')
    else:
        flash('นำผู้ให้บริการออกจากเทมเพลตแล้ว', 'success')

    return redirect_to_template_settings(template_id)


# ===== PROVIDER SCHEDULES =====

def _parse_days_of_week():
    days = []
    for value in request.form.getlist('days_of_week'):
        try:
            days.append(int(value))
        except ValueError:
            continue
    return sorted(set(days))


@availability_bp.route('/availability/template/<int:template_id>/schedules/add', methods=['POST'])
@login_required
def add_provider_schedule(template_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    try:
        provider_id = int(request.form.get('provider_id', ''))
    except (TypeError, ValueError):
        flash('กรุณาเลือกผู้ให้บริการ', 'error')
        return redirect_to_template_settings(template_id)

    effective_date = request.form.get('effective_date')
    if not effective_date:
        flash('กรุณาระบุวันที่เริ่มต้น', 'error')
        return redirect_to_template_settings(template_id)

    days_of_week = _parse_days_of_week()
    if not days_of_week:
        flash('ต้องเลือกอย่างน้อย 1 วันทำการ', 'error')
        return redirect_to_template_settings(template_id)

    payload = {
        'provider_id': provider_id,
        'effective_date': effective_date,
        'end_date': request.form.get('end_date') or None,
        'days_of_week': days_of_week,
        'recurrence_pattern': request.form.get('recurrence_pattern') or None,
        'custom_start_time': request.form.get('custom_start_time') or None,
        'custom_end_time': request.form.get('custom_end_time') or None,
        'schedule_type': request.form.get('schedule_type') or 'regular',
        'notes': request.form.get('notes') or None
    }

    _, error = make_api_request('POST', f'/availability/templates/{template_id}/schedules', payload)

    if error:
        flash(f'ไม่สามารถเพิ่มตารางผู้ให้บริการได้: {error}', 'error')
    else:
        flash('เพิ่มตารางผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/schedules/<int:schedule_id>/update', methods=['POST'])
@login_required
def update_provider_schedule(template_id, schedule_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    effective_date = request.form.get('effective_date')
    if not effective_date:
        flash('กรุณาระบุวันที่เริ่มต้น', 'error')
        return redirect_to_template_settings(template_id)

    days_of_week = _parse_days_of_week()
    if not days_of_week:
        flash('ต้องเลือกอย่างน้อย 1 วันทำการ', 'error')
        return redirect_to_template_settings(template_id)

    payload = {
        'effective_date': effective_date,
        'end_date': request.form.get('end_date') or None,
        'days_of_week': days_of_week,
        'recurrence_pattern': request.form.get('recurrence_pattern') or None,
        'custom_start_time': request.form.get('custom_start_time') or None,
        'custom_end_time': request.form.get('custom_end_time') or None,
        'schedule_type': request.form.get('schedule_type') or 'regular',
        'notes': request.form.get('notes') or None,
        'is_active': (request.form.get('is_active') or 'on') == 'on'
    }

    _, error = make_api_request('PATCH', f'/availability/templates/{template_id}/schedules/{schedule_id}', payload)

    if error:
        flash(f'ไม่สามารถอัปเดตตารางผู้ให้บริการได้: {error}', 'error')
    else:
        flash('อัปเดตตารางผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_provider_schedule(template_id, schedule_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    is_active = request.form.get('is_active') == 'on'

    payload = {'is_active': is_active}
    _, error = make_api_request('PATCH', f'/availability/templates/{template_id}/schedules/{schedule_id}', payload)

    if error:
        flash(f'ไม่สามารถอัปเดตสถานะตารางได้: {error}', 'error')
    else:
        flash('อัปเดตสถานะตารางสำเร็จ', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_provider_schedule(template_id, schedule_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    _, error = make_api_request('DELETE', f'/availability/templates/{template_id}/schedules/{schedule_id}')

    if error:
        flash(f'ไม่สามารถลบตารางได้: {error}', 'error')
    else:
        flash('ลบตารางผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


# ===== RESOURCE CAPACITY RULES =====

@availability_bp.route('/availability/template/<int:template_id>/capacities/add', methods=['POST'])
@login_required
def add_resource_capacity(template_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    available_rooms = request.form.get('available_rooms')
    try:
        available_rooms_int = int(available_rooms)
    except (TypeError, ValueError):
        flash('จำนวนห้องที่รองรับต้องเป็นตัวเลข', 'error')
        return redirect_to_template_settings(template_id)

    payload = {
        'specific_date': request.form.get('specific_date') or None,
        'day_of_week': int(request.form.get('day_of_week')) if request.form.get('day_of_week') not in (None, '', 'none') else None,
        'available_rooms': available_rooms_int,
        'max_concurrent_appointments': int(request.form.get('max_concurrent_appointments')) if request.form.get('max_concurrent_appointments') else None,
        'time_slot_start': request.form.get('time_slot_start') or None,
        'time_slot_end': request.form.get('time_slot_end') or None,
        'notes': request.form.get('notes') or None,
        'is_active': request.form.get('is_active') == 'on'
    }

    if payload['specific_date'] is None and payload['day_of_week'] is None:
        flash('กรุณาระบุวันที่เฉพาะเจาะจง หรือเลือกวันในสัปดาห์อย่างน้อยหนึ่งค่า', 'error')
        return redirect_to_template_settings(template_id)

    _, error = make_api_request('POST', f'/availability/templates/{template_id}/capacities', payload)

    if error:
        flash(f'ไม่สามารถเพิ่มข้อจำกัดความจุได้: {error}', 'error')
    else:
        flash('เพิ่มข้อจำกัดความจุเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/capacities/<int:capacity_id>/toggle', methods=['POST'])
@login_required
def toggle_resource_capacity(template_id, capacity_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    is_active = request.form.get('is_active') == 'on'
    payload = {'is_active': is_active}

    _, error = make_api_request('PATCH', f'/availability/templates/{template_id}/capacities/{capacity_id}', payload)

    if error:
        flash(f'ไม่สามารถอัปเดตข้อจำกัดความจุได้: {error}', 'error')
    else:
        flash('อัปเดตสถานะข้อจำกัดความจุเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/capacities/<int:capacity_id>/update', methods=['POST'])
@login_required
def update_resource_capacity(template_id, capacity_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    available_rooms = request.form.get('available_rooms')
    try:
        available_rooms_int = int(available_rooms)
    except (TypeError, ValueError):
        flash('จำนวนห้องที่รองรับต้องเป็นตัวเลข', 'error')
        return redirect_to_template_settings(template_id)

    day_raw = request.form.get('day_of_week')
    specific_date = request.form.get('specific_date') or None
    day_value = None
    if day_raw not in (None, '', 'none'):
        try:
            day_value = int(day_raw)
        except ValueError:
            flash('วันในสัปดาห์ไม่ถูกต้อง', 'error')
            return redirect_to_template_settings(template_id)

    if not specific_date and day_value is None:
        flash('กรุณาระบุวันที่เฉพาะเจาะจงหรือเลือกวันในสัปดาห์อย่างน้อยหนึ่งค่า', 'error')
        return redirect_to_template_settings(template_id)

    payload = {
        'available_rooms': available_rooms_int,
        'max_concurrent_appointments': int(request.form.get('max_concurrent_appointments')) if request.form.get('max_concurrent_appointments') else None,
        'specific_date': specific_date,
        'day_of_week': day_value,
        'time_slot_start': request.form.get('time_slot_start') or None,
        'time_slot_end': request.form.get('time_slot_end') or None,
        'notes': request.form.get('notes') or None,
        'is_active': request.form.get('is_active') == 'on'
    }

    _, error = make_api_request('PATCH', f'/availability/templates/{template_id}/capacities/{capacity_id}', payload)

    if error:
        flash(f'ไม่สามารถอัปเดตข้อจำกัดความจุได้: {error}', 'error')
    else:
        flash('อัปเดตข้อจำกัดความจุเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/capacities/<int:capacity_id>/delete', methods=['POST'])
@login_required
def delete_resource_capacity(template_id, capacity_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    _, error = make_api_request('DELETE', f'/availability/templates/{template_id}/capacities/{capacity_id}')

    if error:
        flash(f'ไม่สามารถลบข้อจำกัดความจุได้: {error}', 'error')
    else:
        flash('ลบข้อจำกัดความจุเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


# ===== PROVIDER LEAVES =====

@availability_bp.route('/availability/template/<int:template_id>/provider-leaves/add', methods=['POST'])
@login_required
def add_provider_leave(template_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    try:
        provider_id = int(request.form.get('provider_id', ''))
    except (TypeError, ValueError):
        flash('กรุณาเลือกผู้ให้บริการ', 'error')
        return redirect_to_template_settings(template_id)

    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if not start_date or not end_date:
        flash('กรุณาระบุวันที่เริ่มและสิ้นสุดการลา', 'error')
        return redirect_to_template_settings(template_id)

    payload = {
        'provider_id': provider_id,
        'start_date': start_date,
        'end_date': end_date,
        'leave_type': request.form.get('leave_type') or None,
        'reason': request.form.get('reason') or None,
        'approved_by': request.form.get('approved_by') or None,
        'is_approved': request.form.get('is_approved') == 'on'
    }

    _, error = make_api_request('POST', f'/availability/providers/{provider_id}/leaves', payload)

    if error:
        flash(f'ไม่สามารถบันทึกการลาของผู้ให้บริการได้: {error}', 'error')
    else:
        flash('บันทึกการลาของผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/availability/template/<int:template_id>/provider-leaves/<int:provider_id>/<int:leave_id>/delete', methods=['POST'])
@login_required
def delete_provider_leave(template_id, provider_id, leave_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    _, error = make_api_request('DELETE', f'/availability/providers/{provider_id}/leaves/{leave_id}')

    if error:
        flash(f'ไม่สามารถลบข้อมูลการลาได้: {error}', 'error')
    else:
        flash('ลบข้อมูลการลาของผู้ให้บริการแล้ว', 'success')

    return redirect_to_template_settings(template_id)


@availability_bp.route('/api/providers/<int:provider_id>/leaves')
@login_required
def get_provider_leaves(provider_id):
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        return jsonify({'error': 'Unauthorized'}), 401

    leaves_data, error = make_api_request('GET', f'/availability/providers/{provider_id}/leaves')

    if error:
        return jsonify({'error': error}), 500

    return jsonify(leaves_data or {'leaves': []})

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
