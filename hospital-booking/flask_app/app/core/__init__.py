# flask_app/app/core/__init__.py
from .tenant_manager import TenantManager, with_tenant

__all__ = ['TenantManager', 'with_tenant']