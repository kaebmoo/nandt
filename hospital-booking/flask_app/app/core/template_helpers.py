# flask_app/app/core/template_helpers.py

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