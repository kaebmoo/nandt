# flask_app/app/core/template_helpers.py
from datetime import datetime

from flask import g, session
from .tenant_manager import TenantManager

def get_navigation_context():
    """Get context for navigation links"""
    from .. import get_current_user
    
    _, subdomain = TenantManager.get_tenant_context()
    current_user = get_current_user()
    
    # Fallback to user's hospital if no subdomain
    if not subdomain and current_user and current_user.hospital:
        subdomain = current_user.hospital.subdomain
    
    return {
        'subdomain': subdomain,
        'current_user': current_user,
        'is_logged_in': 'user_id' in session
    }

# Register as template global
def register_template_helpers(app):
    @app.context_processor
    def inject_navigation_context():
        return {'nav': get_navigation_context()}
    
# flask_app/app/core/template_helpers.py
"""Template filters และ helpers สำหรับใช้ทั่วทั้ง application"""

def register_template_filters(app):
    """ลงทะเบียน template filters ทั้งหมดกับ Flask app"""
    
    @app.template_filter('day_name_th')
    def day_name_th_filter(day_number):
        """แปลงเลขวันเป็นชื่อวันภาษาไทย"""
        day_names = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์']
        return day_names[day_number] if 0 <= day_number < 7 else ''

    @app.template_filter('day_name_th_short')
    def day_name_th_short_filter(day_number):
        """แปลงเลขวันเป็นชื่อวันภาษาไทยแบบสั้น"""
        day_names = ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส']
        return day_names[day_number] if 0 <= day_number < 7 else ''

    @app.template_filter('format_time_range')
    def format_time_range_filter(start_time, end_time):
        """Format ช่วงเวลา"""
        return f"{start_time} - {end_time}"

    @app.template_filter('thai_date')
    def thai_date_filter(date):
        """แปลงวันที่เป็นรูปแบบ dd/mm/yyyy"""
        if not date:
            return ''
        
        try:
            # ถ้าเป็น string
            if isinstance(date, str):
                # ถ้าเป็น yyyy-mm-dd format
                if '-' in date and len(date.split('-')[0]) == 4:
                    parts = date.split('-')
                    if len(parts) == 3:
                        return f"{parts[2]}/{parts[1]}/{parts[0]}"
                # ถ้าเป็น dd/mm/yyyy อยู่แล้ว
                elif '/' in date:
                    return date
                # พยายาม parse
                else:
                    try:
                        dt = datetime.strptime(date[:10], '%Y-%m-%d')
                        return dt.strftime('%d/%m/%Y')
                    except:
                        return date
            
            # ถ้าเป็น datetime/date object
            elif hasattr(date, 'strftime'):
                return date.strftime('%d/%m/%Y')
            
            return str(date)
        except:
            return str(date)

    @app.template_filter('thai_time')
    def thai_time_filter(time):
        """Format เวลา"""
        if not time:
            return ''
        
        try:
            if isinstance(time, str):
                return time[:5]  # HH:MM
            return time.strftime('%H:%M')
        except:
            return str(time)


def register_template_context(app):
    """ลงทะเบียน context processors"""
    
    @app.context_processor
    def inject_template_vars():
        """Context processor สำหรับส่งตัวแปรทั่วไปไป template"""
        return {
            'day_names_th': ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'],
            'day_names_th_short': ['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'],
            'current_year': lambda: datetime.now().year + 543,  # ปี พ.ศ.
        }