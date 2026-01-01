"""
Authentication module for Super Admin application
Handles login, logout, and access control decorators
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from functools import wraps

from shared_db.models import User, UserRole

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """
    Decorator to require login for a route
    Redirects to login page if user is not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณา login ก่อนเข้าใช้งาน', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """
    Decorator to require super admin role
    Checks both authentication and super admin role
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('กรุณา login ก่อนเข้าใช้งาน', 'error')
            return redirect(url_for('auth.login'))

        user = g.db.query(User).filter_by(id=session['user_id']).first()
        if not user or user.role != UserRole.SUPER_ADMIN:
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
            return redirect(url_for('auth.login'))

        # Store current user in g for use in views
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Super Admin login page and handler"""
    # If already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('กรุณากรอกอีเมลและรหัสผ่าน', 'error')
            return render_template('auth/login.html')

        # Query user by email
        user = g.db.query(User).filter_by(email=email).first()

        if user and user.check_password(password):
            # Check if user is super admin
            if user.role != UserRole.SUPER_ADMIN:
                flash('คุณไม่มีสิทธิ์เข้าถึงระบบนี้ (ต้องเป็น Super Admin เท่านั้น)', 'error')
                return render_template('auth/login.html')

            # Login successful
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_email'] = user.email

            flash(f'ยินดีต้อนรับ {user.name}!', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('อีเมลหรือรหัสผ่านไม่ถูกต้อง', 'error')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Logout handler"""
    user_name = session.get('user_name', '')
    session.clear()
    flash(f'ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('auth.login'))
