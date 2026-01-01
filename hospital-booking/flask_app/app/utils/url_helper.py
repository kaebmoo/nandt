# flask_app/app/utils/url_helper.py
from flask import request, g, url_for
import os

def needs_subdomain_param():
    """
    ตรวจสอบว่าต้องใช้ subdomain parameter ในURL หรือไม่
    Returns True ถ้าต้องใช้ query parameter (?subdomain=xxx)
    Returns False ถ้า subdomain อยู่ใน hostname แล้ว
    """
    # ตรวจสอบจาก g.subdomain_from_host ก่อน (ถ้ามี)
    # นี่คือค่าที่ middleware ตั้งไว้แล้ว
    if hasattr(g, 'subdomain_from_host') and g.subdomain_from_host:
        return False  # subdomain อยู่ใน hostname แล้ว ไม่ต้องใช้ param
    
    hostname = request.host.split(':')[0]
    
    # ไม่มี subdomain ใน URL (localhost, 127.0.0.1)
    if '.' not in hostname:
        return True
    
    # ตรวจสอบว่าส่วนแรกเป็น subdomain จริงหรือไม่
    potential_subdomain = hostname.split('.')[0]
    
    # รายการ prefix ที่ไม่ใช่ subdomain ของผู้ให้บริการ
    non_subdomain_prefixes = ['localhost', 'www', 'api', '127', '192', 'app']
    
    # ถ้าเป็น IP address
    if potential_subdomain.isdigit():
        return True
    
    # ถ้าเป็น prefix ที่ไม่ใช่ subdomain
    if potential_subdomain in non_subdomain_prefixes:
        return True
    
    return False

def build_url_with_context(endpoint, **kwargs):
    """
    สร้าง URL พร้อมจัดการ subdomain context อัตโนมัติ
    - ถ้า subdomain อยู่ใน hostname แล้ว จะไม่เพิ่ม query parameter
    - ถ้า subdomain ไม่อยู่ใน hostname จะเพิ่ม ?subdomain=xxx
    
    Args:
        endpoint: Flask endpoint name
        **kwargs: URL parameters รวมถึง subdomain (optional)
    
    Returns:
        URL string ที่จัดการ subdomain แล้ว
    """
    # ดึง subdomain จาก kwargs หรือ g object
    subdomain = kwargs.pop('subdomain', None)
    if not subdomain:
        subdomain = getattr(g, 'subdomain', None)
    
    # เพิ่ม subdomain parameter เฉพาะเมื่อจำเป็น
    if subdomain and needs_subdomain_param():
        kwargs['subdomain'] = subdomain
    
    return url_for(endpoint, **kwargs)

def get_dashboard_url(subdomain):
    """
    สร้าง URL สำหรับ dashboard โดยจัดการ subdomain ตาม environment
    
    Args:
        subdomain: ชื่อ subdomain ของผู้ให้บริการ
    
    Returns:
        URL string สำหรับ redirect ไป dashboard
    """
    if not subdomain:
        return '/dashboard'
    
    hostname = request.host.split(':')[0]
    port = request.host.split(':')[1] if ':' in request.host else ''
    
    # ตรวจสอบว่าเป็น development mode หรือไม่
    is_development = (
        hostname in ['localhost', '127.0.0.1'] or 
        hostname.startswith('192.168.') or
        hostname.startswith('10.') or
        os.environ.get('ENVIRONMENT', 'development') == 'development'
    )
    
    # ตรวจสอบว่า subdomain อยู่ใน URL แล้วหรือไม่
    has_subdomain = '.' in hostname and hostname.split('.')[0] == subdomain
    
    if has_subdomain:
        # Subdomain อยู่ใน URL แล้ว
        return '/dashboard'
    elif is_development:
        # Development mode - ใช้ query parameter
        return f'/dashboard?subdomain={subdomain}'
    else:
        # Production - สร้าง subdomain URL
        base_domain = '.'.join(hostname.split('.')[1:]) if '.' in hostname else hostname
        port_str = f':{port}' if port else ''
        protocol = 'https' if request.is_secure else 'http'
        return f'{protocol}://{subdomain}.{base_domain}{port_str}/dashboard'

# Alias function สำหรับ backward compatibility
def universal_url_for(endpoint, **kwargs):
    """
    Universal URL generator - alias ของ build_url_with_context
    ใช้แทน nav_url และ smart_url_for ทั้งหมด
    """
    return build_url_with_context(endpoint, **kwargs)

# เพิ่มใน url_helper.py
def get_nav_params():
    """
    ดึงค่าที่จำเป็นสำหรับ navigation จาก g object
    """
    from ..auth import get_current_user
    
    return {
        'subdomain': getattr(g, 'subdomain', None),
        'current_user': get_current_user(),
        'is_from_host': getattr(g, 'subdomain_from_host', False)
    }