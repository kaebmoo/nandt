# flask_app/app/core/tenant_manager.py

from flask import request, session, g, redirect, url_for
from functools import wraps
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class TenantManager:
    """Centralized tenant management system"""
    
    @staticmethod
    def get_tenant_context() -> Tuple[Optional[str], Optional[str]]:
        """
        Get tenant context from all possible sources
        Returns: (tenant_schema, subdomain)
        """
        # Priority 1: Check g object (set by middleware)
        if hasattr(g, 'tenant') and hasattr(g, 'subdomain'):
            return g.tenant, g.subdomain
        
        # Priority 2: Query parameter
        subdomain = request.args.get('subdomain') or request.args.get('tenant')
        if subdomain:
            return f"tenant_{subdomain}", subdomain
        
        # Priority 3: Subdomain in hostname
        hostname = request.host.split(':')[0]
        parts = hostname.split('.')
        
        # Check for actual subdomain (not www, api, localhost)
        if len(parts) > 1:
            potential_subdomain = parts[0]
            # Check if it's a valid subdomain (not reserved words or IPs)
            if potential_subdomain not in ['www', 'api'] and not potential_subdomain.isdigit():
                # Special case for *.localhost - treat as valid subdomain
                if len(parts) == 2 and parts[1] == 'localhost':
                    subdomain = potential_subdomain
                    return f"tenant_{subdomain}", subdomain
                # Normal subdomain for production
                elif potential_subdomain not in ['localhost', '127', '192']:
                    subdomain = potential_subdomain
                    return f"tenant_{subdomain}", subdomain
        
        # Priority 4: User's default hospital (for logged-in users)
        if 'user_id' in session:
            subdomain = TenantManager._get_user_default_subdomain()
            if subdomain:
                return f"tenant_{subdomain}", subdomain
        
        return None, None
    
    @staticmethod
    def _get_user_default_subdomain() -> Optional[str]:
        """Get subdomain from logged-in user's hospital"""
        from .. import SessionLocal
        from ..models import User, Hospital
        
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(id=session['user_id']).first()
            if user and user.hospital_id:
                hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
                if hospital:
                    return hospital.subdomain
        except Exception as e:
            logger.error(f"Error getting user's subdomain: {e}")
        finally:
            db.close()
        
        return None
    
    @staticmethod
    def ensure_tenant_url(subdomain: str) -> str:
        """
        Generate proper URL with tenant context
        Handles both development (query param) and production (subdomain)
        """
        is_development = 'localhost' in request.host or '127.0.0.1' in request.host
        
        if is_development:
            # Development: Use query parameter
            from werkzeug.urls import url_encode
            args = request.args.to_dict()
            args['subdomain'] = subdomain
            query_string = url_encode(args)
            return f"{request.path}?{query_string}"
        else:
            # Production: Use subdomain
            base_domain = '.'.join(request.host.split('.')[1:])
            return f"http://{subdomain}.{base_domain}{request.path}"
    
    @staticmethod
    def validate_tenant_access(subdomain: str) -> bool:
        """Check if current user has access to the tenant"""
        if not subdomain or 'user_id' not in session:
            return False
        
        from .. import SessionLocal
        from ..models import User, Hospital
        
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(id=session['user_id']).first()
            if not user or not user.hospital_id:
                return False
            
            hospital = db.query(Hospital).filter_by(id=user.hospital_id).first()
            if not hospital:
                return False
            
            # User can access their own hospital
            return hospital.subdomain == subdomain
            
        except Exception as e:
            logger.error(f"Error validating tenant access: {e}")
            return False
        finally:
            db.close()


def with_tenant(require_access=True, redirect_on_missing=True):
    """
    Decorator to ensure tenant context exists and user has access
    
    Args:
        require_access: Check if user has permission to access the tenant
        redirect_on_missing: Redirect to proper URL if subdomain is missing
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from ..auth import get_current_user
            
            # Get tenant context
            tenant_schema, subdomain = TenantManager.get_tenant_context()
            
            # If no subdomain and user is logged in, try to use their default
            if not subdomain and 'user_id' in session:
                user = get_current_user()
                if user and user.hospital:
                    subdomain = user.hospital.subdomain
                    
                    # Redirect to URL with subdomain
                    if redirect_on_missing:
                        return redirect(url_for(request.endpoint, 
                                              subdomain=subdomain,
                                              **request.view_args))
            
            # Validate access if required
            if require_access and subdomain:
                if not TenantManager.validate_tenant_access(subdomain):
                    from flask import flash
                    flash('คุณไม่มีสิทธิ์เข้าถึงโรงพยาบาลนี้', 'error')
                    return redirect(url_for('main.index'))
            
            # Set context for use in views
            g.tenant_schema = f"tenant_{subdomain}" if subdomain else None
            g.subdomain = subdomain
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator