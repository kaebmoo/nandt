# flask_app/app/utils/url_helper.py
from flask import request
import os

def get_dashboard_url(subdomain):
    """
    Generate proper dashboard URL based on environment
    - Development: Use query parameter
    - Production/Subdomain: Use subdomain in URL
    """
    hostname = request.host.split(':')[0]
    port = request.host.split(':')[1] if ':' in request.host else ''
    
    # Check if we're in development mode
    is_development = (
        hostname in ['localhost', '127.0.0.1'] or 
        hostname.startswith('192.168.') or
        os.environ.get('ENVIRONMENT', 'development') == 'development'
    )
    
    # Check if subdomain is already in the URL
    has_subdomain = '.' in hostname and hostname.split('.')[0] == subdomain
    
    if has_subdomain:
        # Subdomain already in URL, no need for query param
        return '/dashboard'
    elif is_development:
        # Development mode - use query parameter
        return f'/dashboard?subdomain={subdomain}'
    else:
        # Production - construct subdomain URL
        base_domain = '.'.join(hostname.split('.')[1:]) if '.' in hostname else hostname
        port_str = f':{port}' if port else ''
        protocol = 'https' if request.is_secure else 'http'
        return f'{protocol}://{subdomain}.{base_domain}{port_str}/dashboard'

def needs_subdomain_param():
    """Check if we need subdomain parameter in URL"""
    hostname = request.host.split(':')[0]
    
    # Need param if no subdomain in URL
    if '.' not in hostname:
        return True
    
    # Check if first part is a valid subdomain
    potential_subdomain = hostname.split('.')[0]
    if potential_subdomain in ['localhost', 'www', 'api', '127', '192']:
        return True
    
    return False

def build_url_with_context(endpoint, **kwargs):
    """Build URL with appropriate tenant context"""
    from flask import url_for, g
    
    # Get current subdomain
    subdomain = kwargs.pop('subdomain', None)
    if not subdomain:
        subdomain = getattr(g, 'subdomain', None)
    
    # Only add subdomain param if needed
    if subdomain and needs_subdomain_param():
        kwargs['subdomain'] = subdomain
    
    return url_for(endpoint, **kwargs)
