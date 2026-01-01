"""
Super Admin Flask Application
Tenant management system for hospital booking platform
"""

from flask import Flask, g
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv

from shared_db.database import SessionLocal

load_dotenv()

def create_app():
    """Create and configure the Super Admin Flask application"""
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), '..', 'admin_session')
    app.config['SESSION_PERMANENT'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = 7200  # 2 hours

    # CSRF Configuration - รองรับ X-CSRFToken header
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']
    app.config['WTF_CSRF_TIME_LIMIT'] = None  # ไม่จำกัดเวลา CSRF token

    # Initialize extensions
    Session(app)
    csrf = CSRFProtect(app)

    # Ensure session directory exists
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

    # Database session management
    @app.before_request
    def setup_db_session():
        """Setup database session for each request"""
        if 'db' not in g:
            g.db = SessionLocal()

    @app.teardown_request
    def teardown_db_session(exception=None):
        """Clean up database session after each request"""
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # Register blueprints
    from admin_app.auth import auth_bp
    from admin_app.tenant_routes import tenant_bp
    from admin_app.dashboard_routes import dashboard_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(tenant_bp, url_prefix='/tenants')
    app.register_blueprint(dashboard_bp, url_prefix='/')

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        g.db.rollback()
        return render_template('errors/500.html'), 500

    return app
