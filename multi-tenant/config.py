# config.py - Enhanced Configuration Management (Complete)
import os
from dotenv import load_dotenv
import secrets
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler
from flask import request, g
from flask_login import current_user
import traceback

# Load environment variables from .env file
load_dotenv()

# Custom Logging Filter for Request-specific Information
class RequestInfoFilter(logging.Filter):
    def filter(self, record):
        """
        Injects request-specific information into the log record.
        This allows formatters to access details like user ID, IP address, etc.
        """
        record.user_id = 'Anonymous'
        record.ip_address = 'N/A'
        record.user_agent = 'N/A'
        record.url = 'N/A'
        record.method = 'N/A'
        record.traceback = ''

        try:
            if request:
                record.ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                record.user_agent = request.headers.get('User-Agent', 'N/A')
                record.url = request.url
                record.method = request.method

            from flask_login import current_user as _current_user
            if _current_user and _current_user.is_authenticated:
                record.user_id = _current_user.get_id()
            
            if record.exc_info:
                import traceback
                record.traceback = traceback.format_exc()

        except RuntimeError:
            pass
        except Exception as e:
            print(f"Error in RequestInfoFilter: {e}")

        return True

class Config:
    """Base configuration class for the application."""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    DEBUG = False
    TESTING = False
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///nuddee_saas.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'pool_size': 10,
        'max_overflow': 20,
        'echo': False
    }
    
    # Redis Configuration
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Cache Configuration
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Session Configuration
    SESSION_TYPE = 'redis'
    SESSION_REDIS = REDIS_URL
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'nuddee:'
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # File Upload Configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt', 'pdf', 'doc', 'docx'}
    
    # TeamUp API Configuration - UPDATED
    MASTER_TEAMUP_API = os.getenv('MASTER_TEAMUP_API')
    TEMPLATE_CALENDAR_KEY = os.getenv('TEMPLATE_CALENDAR_KEY')
    TEAMUP_PLAN = os.getenv('TEAMUP_PLAN', 'free')
    TEAMUP_RATE_LIMIT = 100
    TEAMUP_ADMIN_EMAIL = os.getenv('TEAMUP_ADMIN_EMAIL') # NEW
    TEAMUP_ADMIN_PASSWORD = os.getenv('TEAMUP_ADMIN_PASSWORD') # NEW
    TEAMUP_APP_NAME = os.getenv('TEAMUP_APP_NAME', 'NudDeeSaaS') # NEW
    TEAMUP_DEVICE_ID = os.getenv('TEAMUP_DEVICE_ID', 'NudDeeServer') # NEW
    
    # Stripe Configuration
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    STRIPE_API_VERSION = '2023-10-16'
    
    # Email Configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@nuddee.com')
    MAIL_MAX_EMAILS = 100
    
    # Security Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False
    
    # Rate Limiting Configuration
    RATELIMIT_STORAGE_URL = REDIS_URL
    RATELIMIT_DEFAULT = "100 per hour"
    RATELIMIT_HEADERS_ENABLED = True
    
    # Application URLs
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')
    FRONTEND_URL = os.getenv('FRONTEND_URL', APP_URL)
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/nuddee_saas.log')
    LOG_MAX_SIZE = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 10
    
    # Monitoring Configuration
    SENTRY_DSN = os.getenv('SENTRY_DSN')
    NEW_RELIC_LICENSE_KEY = os.getenv('NEW_RELIC_LICENSE_KEY')
    
    # Business Logic Configuration
    TRIAL_PERIOD_DAYS = 14
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCKOUT_DURATION = timedelta(minutes=30)
    PASSWORD_RESET_EXPIRY = timedelta(hours=1)
    
    # Feature Flags
    ENABLE_2FA = os.getenv('ENABLE_2FA', 'True').lower() == 'true'
    ENABLE_EMAIL_VERIFICATION = os.getenv('ENABLE_EMAIL_VERIFICATION', 'True').lower() == 'true'
    ENABLE_AUDIT_LOGGING = os.getenv('ENABLE_AUDIT_LOGGING', 'True').lower() == 'true'
    ENABLE_ANALYTICS = os.getenv('ENABLE_ANALYTICS', 'False').lower() == 'true'
    
    # API Configuration
    API_RATE_LIMIT = "1000 per hour"
    API_VERSION = "v1"
    
    # Backup Configuration
    BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', 24))
    BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', 30))
    BACKUP_STORAGE_PATH = os.getenv('BACKUP_STORAGE_PATH', 'backups/')
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration."""
        directories = [
            Config.UPLOAD_FOLDER,
            'logs',
            'backups/teamup',
            'backups/database',
            'temp'
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
        
        Config.validate_config()
        
        if app:
            Config.setup_logging(app)
            
            if Config.SENTRY_DSN:
                Config.setup_sentry(app)
    
    @staticmethod
    def validate_config():
        """Validate critical configuration variables."""
        required_vars = []
        
        if not Config.MASTER_TEAMUP_API:
            required_vars.append('MASTER_TEAMUP_API')
        
        # เพิ่มการตรวจสอบ TEMPLATE_CALENDAR_KEY
        if not Config.TEMPLATE_CALENDAR_KEY:
            required_vars.append('TEMPLATE_CALENDAR_KEY')
        
        if not Config.TEAMUP_ADMIN_EMAIL: # NEW
            required_vars.append('TEAMUP_ADMIN_EMAIL')
        if not Config.TEAMUP_ADMIN_PASSWORD: # NEW
            required_vars.append('TEAMUP_ADMIN_PASSWORD')
        
        if not Config.SECRET_KEY or Config.SECRET_KEY == 'your-super-secret-key-change-this-in-production':
            required_vars.append('SECRET_KEY')
        
        if required_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(required_vars)}")
        
        if os.getenv('FLASK_ENV') == 'production':
            prod_required_vars = [
                'DATABASE_URL',
                'REDIS_URL',
                'STRIPE_SECRET_KEY',
                'MAIL_USERNAME',
                'MAIL_PASSWORD'
            ]
            missing_prod_vars = [var for var in prod_required_vars if not os.getenv(var)]
            if missing_prod_vars:
                raise ValueError(f"Missing required production environment variables: {', '.join(missing_prod_vars)}")
            
            secret_key = os.getenv('SECRET_KEY')
            if len(secret_key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters long in production")
            
            database_url = os.getenv('DATABASE_URL')
            if database_url and database_url.startswith('sqlite'):
                raise ValueError("SQLite is not recommended for production. Use PostgreSQL or MySQL.")
    
    @staticmethod
    def setup_logging(app):
        """Setup application logging handlers."""
        if not app.debug and not app.testing:
            log_dir = os.path.dirname(Config.LOG_FILE)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            if not any(isinstance(f, RequestInfoFilter) for f in app.logger.filters):
                app.logger.addFilter(RequestInfoFilter())
            
            if not app.logger.handlers:
                file_handler = RotatingFileHandler(
                    Config.LOG_FILE, 
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=Config.LOG_BACKUP_COUNT
                )
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
                ))
                file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
                app.logger.addHandler(file_handler)
                
                error_handler = RotatingFileHandler(
                    'logs/nuddee_errors.log',
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=5
                )
                error_formatter = logging.Formatter(
                    '%(asctime)s %(levelname)s: %(message)s\n'
                    'URL: %(url)s (%(method)s)\n'
                    'User: %(user_id)s\n'
                    'IP: %(ip_address)s\n'
                    'User-Agent: %(user_agent)s\n'
                    'Traceback:\n%(traceback)s\n' + '='*80
                )
                error_handler.setFormatter(error_formatter)
                error_handler.setLevel(logging.ERROR)
                app.logger.addHandler(error_handler)

                security_handler = RotatingFileHandler(
                    'logs/nuddee_security.log',
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=10
                )
                security_handler.setFormatter(logging.Formatter(
                    '%(asctime)s SECURITY: %(message)s'
                ))
                security_handler.setLevel(logging.WARNING)
                
                security_logger = logging.getLogger('security')
                security_logger.addHandler(security_handler)
                security_logger.setLevel(logging.WARNING)

            app.logger.setLevel(getattr(logging, Config.LOG_LEVEL))
            app.logger.info('NudDee SaaS Application Logging Initialized')
    
    @staticmethod
    def setup_sentry(app):
        """Setup Sentry error tracking integration."""
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
            
            sentry_sdk.init(
                dsn=Config.SENTRY_DSN,
                integrations=[
                    FlaskIntegration(),
                    SqlalchemyIntegration(),
                ],
                traces_sample_rate=0.1,
                environment=os.getenv('FLASK_ENV', 'production')
            )
            app.logger.info("Sentry error tracking initialized.")
        except ImportError:
            app.logger.warning("Sentry SDK not installed, skipping error tracking setup.")
        except Exception as e:
            app.logger.error(f"Failed to initialize Sentry: {e}")

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///nuddee_dev.db')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'echo': True
    }
    
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    DEBUG_TB_ENABLED = True
    DEBUG_TB_INTERCEPT_REDIRECTS = False
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        
        try:
            from flask_debugtoolbar import DebugToolbarExtension
            toolbar = DebugToolbarExtension()
            toolbar.init_app(app)
            app.logger.info("Flask-DebugToolbar initialized.")
        except ImportError:
            app.logger.warning("Flask-DebugToolbar not installed, skipping debug toolbar setup.")
        except Exception as e:
            app.logger.error(f"Failed to initialize Flask-DebugToolbar: {e}")

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True
    
    RATELIMIT_DEFAULT = "60 per hour"
    API_RATE_LIMIT = "500 per hour"
    
    ENABLE_ANALYTICS = True
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        
        if cls.NEW_RELIC_LICENSE_KEY:
            try:
                import newrelic.agent
                newrelic.agent.initialize()
                app.logger.info("New Relic monitoring initialized.")
            except ImportError:
                app.logger.warning("New Relic agent not installed, skipping monitoring setup.")
            except Exception as e:
                app.logger.error(f"Failed to initialize New Relic: {e}")
        
        import logging
        from logging.handlers import SysLogHandler
        try:
            syslog_handler = SysLogHandler()
            syslog_handler.setLevel(logging.WARNING)
            app.logger.addHandler(syslog_handler)
            app.logger.info("Syslog handler added for production logging.")
        except Exception as e:
            app.logger.error(f"Failed to setup SysLogHandler: {e}")

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    
    MAIL_SUPPRESS_SEND = True
    STRIPE_SECRET_KEY = 'sk_test_fake_key'
    MASTER_TEAMUP_API = 'test_api_key'
    TEMPLATE_CALENDAR_KEY = 'test_template_key'
    
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=1)
    PASSWORD_RESET_EXPIRY = timedelta(minutes=1)

class StagingConfig(ProductionConfig):
    """Staging configuration."""
    DEBUG = True
    
    SQLALCHEMY_DATABASE_URI = os.getenv('STAGING_DATABASE_URL')
    
    RATELIMIT_DEFAULT = "200 per hour"
    
    DEBUG_TB_ENABLED = True
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        try:
            from flask_debugtoolbar import DebugToolbarExtension
            toolbar = DebugToolbarExtension()
            toolbar.init_app(app)
            app.logger.info("Flask-DebugToolbar initialized for staging.")
        except ImportError:
            app.logger.warning("Flask-DebugToolbar not installed, skipping debug toolbar setup for staging.")
        except Exception as e:
            app.logger.error(f"Failed to initialize Flask-DebugToolbar for staging: {e}")

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Get the appropriate configuration class based on the FLASK_ENV environment variable."""
    env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, config['default'])

def load_environment_config():
    """Load additional environment-specific configuration from a .env.<env> file."""
    env = os.getenv('FLASK_ENV', 'development')
    
    env_file = f'.env.{env}'
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
    
    return get_config()

def validate_production_config():
    """Validate critical production configuration variables."""
    if os.getenv('FLASK_ENV') == 'production':
        required_vars = [
            'SECRET_KEY',
            'DATABASE_URL',
            'REDIS_URL',
            'MASTER_TEAMUP_API',
            'TEMPLATE_CALENDAR_KEY',
            'STRIPE_SECRET_KEY',
            'MAIL_USERNAME',
            'MAIL_PASSWORD'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required production environment variables: {', '.join(missing_vars)}")
        
        secret_key = os.getenv('SECRET_KEY')
        if len(secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long in production")
        
        database_url = os.getenv('DATABASE_URL')
        if database_url and database_url.startswith('sqlite'):
            raise ValueError("SQLite is not recommended for production. Use PostgreSQL or MySQL.")

def get_config_value(key, default=None):
    """Get a configuration value from the currently active config class with a fallback default."""
    config_class = get_config()
    return getattr(config_class, key, default)

# Health check configuration
HEALTH_CHECK_CONFIG = {
    'database': True,
    'redis': True,
    'teamup_api': True,
    'stripe_api': False,
    'mail_server': False,
}