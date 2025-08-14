# flask_app/app/helpers/navigation.py

from flask import request, session
from typing import Dict, Optional

class NavigationHelper:
    """Helper class for consistent navigation across the app"""
    
    @staticmethod
    def get_nav_params() -> Dict[str, str]:
        """Get navigation parameters including subdomain"""
        params = {}
        
        # Check multiple sources for subdomain
        subdomain = (
            request.args.get('subdomain') or
            request.args.get('tenant') or
            getattr(request, 'subdomain', None)
        )
        
        # Fallback to user's hospital if logged in
        if not subdomain and 'user_id' in session:
            from ..auth import get_current_user
            user = get_current_user()
            if user and user.hospital:
                subdomain = user.hospital.subdomain
        
        if subdomain:
            params['subdomain'] = subdomain
            
        return params
    
    @staticmethod
    def url_for_with_subdomain(endpoint: str, **kwargs) -> str:
        """Generate URL with subdomain parameter"""
        from flask import url_for
        
        # Get current subdomain
        nav_params = NavigationHelper.get_nav_params()
        
        # Merge with provided kwargs
        if nav_params.get('subdomain') and 'subdomain' not in kwargs:
            kwargs['subdomain'] = nav_params['subdomain']
        
        return url_for(endpoint, **kwargs)