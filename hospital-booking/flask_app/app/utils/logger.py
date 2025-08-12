# flask_app/app/utils/logger.py

import logging
from functools import wraps
from flask import current_app, request

def log_route_access(f):
    """Decorator สำหรับ log การเข้าถึง route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_app.logger.info(f"Route accessed: {request.endpoint} - {request.method} {request.path}")
        current_app.logger.debug(f"Request args: {request.args}")
        
        try:
            result = f(*args, **kwargs)
            current_app.logger.debug(f"Route {request.endpoint} completed successfully")
            return result
        except Exception as e:
            current_app.logger.error(f"Route {request.endpoint} failed: {str(e)}", exc_info=True)
            raise
    
    return decorated_function