# config/logging_config.py
import logging
import logging.handlers
import os
from datetime import datetime
import re

class SecurityFilter(logging.Filter):
    """กรองข้อมูลที่ sensitive ออกจาก logs"""
    SENSITIVE_PATTERNS = [
        r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        r'token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', 
        r'password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        r'secret["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        r'teamup-token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
    ]
    
    def filter(self, record):
        if hasattr(record, 'msg') and record.msg:
            message = str(record.msg)
            for pattern in self.SENSITIVE_PATTERNS:
                message = re.sub(pattern, r'\1: [REDACTED]', message, flags=re.IGNORECASE)
            record.msg = message
        return True

def setup_logging(app):
    """ตั้งค่า logging สำหรับ application"""
    
    # สร้างโฟลเดอร์ logs
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # ตั้งค่าระดับ logging ตาม environment
    log_level = logging.INFO
    if app.config.get('DEBUG'):
        log_level = logging.DEBUG
    elif app.config.get('ENVIRONMENT') == 'production':
        log_level = logging.WARNING
    
    # สร้าง loggers
    app_logger = logging.getLogger('dialysis_scheduler')
    app_logger.setLevel(log_level)
    
    # ลบ handlers เก่า (ถ้ามี)
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
    
    # File handler สำหรับ application logs
    app_file_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/application.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    app_file_handler.setLevel(logging.INFO)
    
    # Error file handler
    error_file_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/error.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    
    # Security file handler
    security_file_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/security.log',
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    security_file_handler.setLevel(logging.WARNING)
    
    # Console handler (สำหรับ development)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Security filter
    security_filter = SecurityFilter()
    app_file_handler.addFilter(security_filter)
    error_file_handler.addFilter(security_filter)
    console_handler.addFilter(security_filter)
    
    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # ตั้งค่า formatters
    app_file_handler.setFormatter(detailed_formatter)
    error_file_handler.setFormatter(detailed_formatter)
    security_file_handler.setFormatter(detailed_formatter)
    console_handler.setFormatter(simple_formatter)
    
    # เพิ่ม handlers
    app_logger.addHandler(app_file_handler)
    app_logger.addHandler(error_file_handler)
    
    # เพิ่ม security handler สำหรับ security logger
    security_logger = logging.getLogger('dialysis_scheduler.security')
    security_logger.addHandler(security_file_handler)
    
    # เพิ่ม console handler สำหรับ development
    if app.config.get('DEBUG'):
        app_logger.addHandler(console_handler)
    
    # ป้องกัน duplicate logs
    app_logger.propagate = False
    
    return app_logger
