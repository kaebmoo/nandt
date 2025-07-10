# utils/error_handlers.py
import logging
import traceback
import uuid
from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger('dialysis_scheduler.errors')
security_logger = logging.getLogger('dialysis_scheduler.security')

class ProductionErrorHandler:
    """จัดการ errors สำหรับ production environment"""
    
    @staticmethod
    def handle_api_error(error, endpoint=None, user_data=None):
        """จัดการ errors สำหรับ API endpoints"""
        error_id = generate_error_id()
        
        # Log detailed error
        logger.error(f"API Error [{error_id}] at {endpoint}: {str(error)}", 
                    exc_info=True, extra={'user_data': user_data})
        
        # Security logging สำหรับ errors ที่อาจเป็น attacks
        if is_potential_attack(error, request):
            security_logger.warning(f"Potential attack detected [{error_id}]: {request.remote_addr}", 
                                   extra={'endpoint': endpoint, 'user_agent': request.headers.get('User-Agent')})
        
        # Return safe error message
        if isinstance(error, HTTPException):
            return jsonify({
                'error': get_safe_error_message(error.code),
                'error_id': error_id
            }), error.code
        
        return jsonify({
            'error': 'เกิดข้อผิดพลาดภายในระบบ',
            'error_id': error_id
        }), 500
    
    @staticmethod
    def handle_form_error(error, form_data=None):
        """จัดการ errors สำหรับ form submissions"""
        error_id = generate_error_id()
        
        # Log error with sanitized form data
        safe_form_data = sanitize_form_data(form_data) if form_data else {}
        logger.error(f"Form Error [{error_id}]: {str(error)}", 
                    extra={'form_data': safe_form_data})
        
        return {
            'error': 'ไม่สามารถประมวลผลข้อมูลได้',
            'error_id': error_id
        }
    
    @staticmethod
    def handle_external_api_error(error, api_name=None, status_code=None):
        """จัดการ errors จาก external APIs"""
        error_id = generate_error_id()
        
        logger.error(f"External API Error [{error_id}] from {api_name}: {str(error)}", 
                    extra={'status_code': status_code})
        
        # ไม่เปิดเผยรายละเอียดของ external API
        return {
            'error': 'ไม่สามารถเชื่อมต่อกับบริการภายนอกได้ในขณะนี้',
            'error_id': error_id
        }

def generate_error_id():
    """สร้าง unique error ID สำหรับ tracking"""
    return str(uuid.uuid4())[:8].upper()

def sanitize_form_data(form_data):
    """ลบข้อมูล sensitive ออกจาก form data"""
    if not form_data:
        return {}
        
    sensitive_fields = ['api_key', 'password', 'token', 'secret', 'teamup_api']
    sanitized = {}
    
    for key, value in form_data.items():
        if any(field in key.lower() for field in sensitive_fields):
            sanitized[key] = '[REDACTED]'
        else:
            sanitized[key] = str(value)[:100] if isinstance(value, str) else str(value)
    
    return sanitized

def get_safe_error_message(status_code):
    """ส่งคืน error message ที่ปลอดภัยตาม status code"""
    safe_messages = {
        400: 'ข้อมูลที่ส่งมาไม่ถูกต้อง',
        401: 'ไม่ได้รับอนุญาตให้เข้าถึง',
        403: 'ไม่มีสิทธิ์ในการดำเนินการนี้',
        404: 'ไม่พบข้อมูลที่ต้องการ',
        429: 'มีการเข้าถึงบ่อยเกินไป กรุณาลองใหม่ในภายหลัง',
        500: 'เกิดข้อผิดพลาดภายในระบบ'
    }
    return safe_messages.get(status_code, 'เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ')

def is_potential_attack(error, request):
    """ตรวจสอบว่า error อาจเกิดจาก attack หรือไม่"""
    attack_patterns = [
        'sql', 'script', 'javascript', 'eval', 'exec',
        'union', 'select', 'drop', 'delete', 'insert',
        '<script', 'javascript:', 'vbscript:'
    ]
    
    error_msg = str(error).lower()
    request_data = str(request.get_data()).lower()
    
    return any(pattern in error_msg or pattern in request_data for pattern in attack_patterns)
