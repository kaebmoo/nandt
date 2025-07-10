# middleware/security.py
import logging
from flask import request, g
import time
import uuid

logger = logging.getLogger('dialysis_scheduler.security')

class SecurityMiddleware:
    """Middleware สำหรับ security และ monitoring"""
    
    def __init__(self, app):
        self.app = app
        self.setup_middleware()
    
    def setup_middleware(self):
        @self.app.before_request
        def log_request():
            g.start_time = time.time()
            g.request_id = self.generate_request_id()
            
            # Log request (without sensitive data)
            safe_data = self.sanitize_request_data(request)
            logger.info(f"Request [{g.request_id}]: {request.method} {request.path}", 
                       extra={'request_data': safe_data})
            
            # Security checks
            self.check_suspicious_requests(request)
        
        @self.app.after_request
        def log_response(response):
            duration = time.time() - g.start_time
            
            logger.info(f"Response [{getattr(g, 'request_id', 'unknown')}]: "
                       f"{response.status_code} in {duration:.3f}s")
            
            # Security headers
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            return response
    
    def generate_request_id(self):
        """สร้าง unique request ID"""
        return str(uuid.uuid4())[:8].upper()
    
    def sanitize_request_data(self, request):
        """ลบข้อมูล sensitive จาก request data"""
        sensitive_fields = ['api_key', 'password', 'token', 'secret']
        
        # Form data
        form_data = {}
        if request.form:
            for key, value in request.form.items():
                if any(field in key.lower() for field in sensitive_fields):
                    form_data[key] = '[REDACTED]'
                else:
                    form_data[key] = str(value)[:100] if len(str(value)) > 100 else str(value)
        
        # Query parameters
        args_data = {}
        for key, value in request.args.items():
            if any(field in key.lower() for field in sensitive_fields):
                args_data[key] = '[REDACTED]'
            else:
                args_data[key] = str(value)[:100] if len(str(value)) > 100 else str(value)
        
        return {
            'form_data': form_data,
            'args': args_data,
            'user_agent': request.headers.get('User-Agent', '')[:200],
            'ip': request.remote_addr,
            'content_length': request.content_length
        }
    
    def check_suspicious_requests(self, request):
        """ตรวจสอบ requests ที่น่าสงสัย"""
        suspicious_patterns = [
            'union select', 'drop table', 'exec(', 'eval(',
            '<script>', 'javascript:', 'vbscript:',
            '../', '..\\', '/etc/passwd', 'cmd.exe'
        ]
        
        # ตรวจสอบ URL และ parameters
        full_url = request.full_path.lower()
        request_data = str(request.get_data()).lower()
        
        for pattern in suspicious_patterns:
            if pattern in full_url or pattern in request_data:
                logger.warning(f"Suspicious request detected from {request.remote_addr}: "
                             f"Pattern '{pattern}' found in {request.method} {request.path}",
                             extra={
                                 'ip': request.remote_addr,
                                 'user_agent': request.headers.get('User-Agent', ''),
                                 'pattern': pattern
                             })
                break
