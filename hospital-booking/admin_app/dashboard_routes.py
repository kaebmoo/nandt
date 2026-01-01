"""
Dashboard routes for Super Admin application
Display overview statistics and recent activity
"""

from flask import Blueprint, render_template, g
from shared_db.models import Hospital, User, HospitalStatus, UserRole
from admin_app.auth import super_admin_required

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@super_admin_required
def index():
    """Super Admin Dashboard - Overview statistics"""

    # Overall statistics
    total_tenants = g.db.query(Hospital).filter(
        Hospital.status != HospitalStatus.DELETED
    ).count()

    active_tenants = g.db.query(Hospital).filter_by(
        status=HospitalStatus.ACTIVE
    ).count()

    inactive_tenants = g.db.query(Hospital).filter_by(
        status=HospitalStatus.INACTIVE
    ).count()

    # Count hospital admins (users with hospital_id)
    total_users = g.db.query(User).filter(
        User.hospital_id.isnot(None),
        User.role == UserRole.HOSPITAL_ADMIN
    ).count()

    # Count super admins
    total_super_admins = g.db.query(User).filter_by(
        role=UserRole.SUPER_ADMIN
    ).count()

    # Recent tenants (last 5)
    recent_tenants = g.db.query(Hospital).filter(
        Hospital.status != HospitalStatus.DELETED
    ).order_by(Hospital.created_at.desc()).limit(5).all()

    # Statistics dictionary
    stats = {
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'inactive_tenants': inactive_tenants,
        'total_users': total_users,
        'total_super_admins': total_super_admins
    }

    return render_template(
        'dashboard/index.html',
        stats=stats,
        recent_tenants=recent_tenants
    )
