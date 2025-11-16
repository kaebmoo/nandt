# flask_app/app/provider_routes.py

import os
import requests
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort, g, make_response
from .auth import login_required, check_tenant_access
from .core.tenant_manager import with_tenant
from .forms import ProviderForm
from .auth import get_current_user
from .core.tenant_manager import TenantManager
from .utils.url_helper import build_url_with_context

# สร้าง Blueprint สำหรับ provider management
provider_bp = Blueprint('providers', __name__, url_prefix='/settings')

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


# ===== PROVIDER LIST =====
@provider_bp.route('/providers')
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def provider_list():
    """หน้าแสดงรายการผู้ให้บริการทั้งหมด"""
    current_user = get_current_user()
    subdomain = g.subdomain

    if not current_user:
        flash('กรุณาเข้าสู่ระบบ', 'error')
        return redirect(url_for('auth.login'))

    # ดึงรายการผู้ให้บริการจาก API
    providers_data, error = make_api_request('GET', '/providers')

    if error:
        flash(f'เกิดข้อผิดพลาดในการโหลดข้อมูล: {error}', 'error')
        providers = []
    else:
        providers = providers_data.get('providers', [])

    # สร้าง response และเพิ่ม cache control headers
    response = make_response(render_template('settings/providers/index.html',
                                            current_user=current_user,
                                            providers=providers,
                                            subdomain=subdomain))

    # ป้องกัน browser cache
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


# ===== CREATE PROVIDER =====
@provider_bp.route('/providers/new', methods=['GET', 'POST'])
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def create_provider():
    """สร้างผู้ให้บริการใหม่"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    form = ProviderForm()

    if form.validate_on_submit():
        # เตรียมข้อมูลส่งไป API
        provider_data = {
            'name': form.name.data,
            'title': form.title.data,
            'department': form.department.data,
            'email': form.email.data,
            'phone': form.phone.data,
            'bio': form.bio.data,
            'is_active': form.is_active.data
        }

        # ส่งข้อมูลไป API
        api_data, error = make_api_request('POST', '/providers', provider_data)

        if error:
            flash(f'เกิดข้อผิดพลาดในการสร้างผู้ให้บริการ: {error}', 'error')
        else:
            flash('สร้างผู้ให้บริการเรียบร้อยแล้ว!', 'success')
            return redirect(build_url_with_context('providers.provider_list'))

    return render_template('settings/providers/form.html',
                         form=form,
                         current_user=current_user,
                         action='create',
                         page_title='เพิ่มผู้ให้บริการใหม่')


# ===== EDIT PROVIDER =====
@provider_bp.route('/providers/<int:provider_id>/edit', methods=['GET', 'POST'])
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def edit_provider(provider_id):
    """แก้ไขข้อมูลผู้ให้บริการ"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    # ดึงข้อมูลผู้ให้บริการจาก API
    provider_data, error = make_api_request('GET', f'/providers/{provider_id}')

    if error or not provider_data:
        flash(f'ไม่สามารถโหลดข้อมูลผู้ให้บริการได้: {error}', 'error')
        return redirect(build_url_with_context('providers.provider_list'))

    form = ProviderForm(request.form)

    if form.validate_on_submit():
        # เตรียมข้อมูลส่งไป API
        update_data = {
            'name': form.name.data,
            'title': form.title.data,
            'department': form.department.data,
            'email': form.email.data,
            'phone': form.phone.data,
            'bio': form.bio.data,
            'is_active': form.is_active.data
        }

        # ส่งข้อมูลไป API
        api_data, error = make_api_request('PUT', f'/providers/{provider_id}', update_data)

        if error:
            flash(f'เกิดข้อผิดพลาดในการแก้ไข: {error}', 'error')
        else:
            flash('แก้ไขข้อมูลผู้ให้บริการเรียบร้อยแล้ว!', 'success')
            return redirect(build_url_with_context('providers.provider_list'))

    # เติมข้อมูลลงในฟอร์ม (สำหรับ GET request)
    if not form.is_submitted():
        form.name.data = provider_data.get('name')
        form.title.data = provider_data.get('title')
        form.department.data = provider_data.get('department')
        form.email.data = provider_data.get('email')
        form.phone.data = provider_data.get('phone')
        form.bio.data = provider_data.get('bio')
        form.is_active.data = provider_data.get('is_active', True)

    return render_template('settings/providers/form.html',
                         form=form,
                         current_user=current_user,
                         action='edit',
                         provider_id=provider_id,
                         page_title=f'แก้ไขผู้ให้บริการ: {provider_data.get("name")}')


# ===== DELETE PROVIDER =====
@provider_bp.route('/providers/<int:provider_id>/delete', methods=['POST'])
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def delete_provider(provider_id):
    """ลบผู้ให้บริการ"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    # ส่งคำขอลบไป API
    api_data, error = make_api_request('DELETE', f'/providers/{provider_id}')

    if error:
        # API จะส่ง error กลับมาถ้าผู้ให้บริการมี appointments
        # และจะทำ soft delete (deactivate) แทน
        if "deactivated" in str(error).lower():
            flash(f'{error}', 'warning')
        elif "404" in str(error) or "not found" in str(error).lower():
            flash('ไม่พบผู้ให้บริการนี้', 'error')
        else:
            flash(f'เกิดข้อผิดพลาดในการลบ: {error}', 'error')
    else:
        flash('ลบผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect(build_url_with_context('providers.provider_list'))


# ===== TOGGLE ACTIVE =====
@provider_bp.route('/providers/<int:provider_id>/toggle', methods=['POST'])
@login_required
@with_tenant(require_access=True, redirect_on_missing=True)
def toggle_provider(provider_id):
    """เปิด/ปิดการใช้งานผู้ให้บริการ"""
    current_user = get_current_user()
    tenant_schema, subdomain = TenantManager.get_tenant_context()

    if not current_user or not check_tenant_access(subdomain):
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))

    # ส่งคำขอ toggle ไป API
    api_data, error = make_api_request('PATCH', f'/providers/{provider_id}/toggle')

    if error:
        flash(f'เกิดข้อผิดพลาด: {error}', 'error')
    else:
        status = "เปิดใช้งาน" if api_data.get('is_active') else "ปิดใช้งาน"
        flash(f'{status}ผู้ให้บริการเรียบร้อยแล้ว', 'success')

    return redirect(build_url_with_context('providers.provider_list'))


# ===== ERROR HANDLERS =====
@provider_bp.errorhandler(404)
def not_found_error(error):
    flash('ไม่พบหน้าที่ต้องการ', 'error')
    return redirect(build_url_with_context('providers.provider_list'))

@provider_bp.errorhandler(500)
def internal_error(error):
    flash('เกิดข้อผิดพลาดภายในระบบ', 'error')
    return redirect(build_url_with_context('providers.provider_list'))
