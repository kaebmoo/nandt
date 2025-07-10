# config.py - Enhanced Configuration Management
import os
from dotenv import load_dotenv
import secrets
from datetime import timedelta
import logging # Added for setup_logging
from logging.handlers import RotatingFileHandler # Added for setup_logging
from flask import request, g # Removed current_user from here
from flask_login import current_user # Added this line to import current_user from flask_login
import traceback # Ensure traceback is imported if you use traceback.format_exc()

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
        record.traceback = '' # Initialize with empty string

        try:
            if request: # Check if request context is available
                record.ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                record.user_agent = request.headers.get('User-Agent', 'N/A')
                record.url = request.url
                record.method = request.method

            # current_user might not be available if not in an app context or logged in
            # Accessing current_user should be wrapped in a check
            from flask_login import current_user as _current_user # Import here to avoid circular dependency if app is initializing
            if _current_user and _current_user.is_authenticated:
                record.user_id = _current_user.get_id()
            
            # For traceback, if exc_info is present, format it
            if record.exc_info:
                import traceback # Re-import here to ensure it's available for this specific use
                record.traceback = traceback.format_exc()

        except RuntimeError:
            # This can happen if the filter is used outside of a request context (e.g., during startup)
            pass
        except Exception as e:
            # Catch any other unexpected errors during filter processing
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
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Disable Flask-SQLAlchemy event system for performance
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300, # Recycle connections after 300 seconds
        'pool_pre_ping': True, # Test connections before use
        'pool_size': 10, # Max number of connections in the pool
        'max_overflow': 20, # Max number of connections that can be opened beyond pool_size
        'echo': False # Set to True to log all SQL statements (for debugging)
    }
    
    # Redis Configuration (Used for Cache and Session)
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Cache Configuration (using Flask-Caching)
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300 # Default cache timeout in seconds (5 minutes)
    
    # Session Configuration (using Flask-Session with Redis)
    SESSION_TYPE = 'redis'
    SESSION_REDIS = REDIS_URL
    SESSION_PERMANENT = False # Session will expire when browser is closed
    SESSION_USE_SIGNER = True # Sign the session cookie to prevent tampering
    SESSION_KEY_PREFIX = 'nuddee:' # Prefix for session keys in Redis
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True # Prevent client-side JavaScript access to the cookie
    SESSION_COOKIE_SAMESITE = 'Lax' # Protect against CSRF attacks
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24) # Lifetime for permanent sessions
    
    # File Upload Configuration
    # Base directory for uploads, relative to the config.py file
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit for file uploads
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt', 'pdf', 'doc', 'docx'} # Added more common document types
    
    # TeamUp API Configuration
    MASTER_TEAMUP_API = os.getenv('MASTER_TEAMUP_API') # Master API key for TeamUp
    TEAMUP_PLAN = os.getenv('TEAMUP_PLAN', 'free') # Current TeamUp plan (e.g., 'free', 'premium')
    TEAMUP_RATE_LIMIT = 100  # requests per minute for TeamUp API calls
    
    # Stripe Configuration (for billing and subscriptions)
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    STRIPE_API_VERSION = '2023-10-16' # Recommended API version for Stripe
    
    # Email Configuration (for sending notifications, password resets)
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true' # Use TLS encryption
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true' # Use SSL encryption
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@nuddee.com')
    MAIL_MAX_EMAILS = 100 # Max emails to send in a batch (if applicable)
    
    # Security Configuration
    WTF_CSRF_ENABLED = True # Enable CSRF protection for forms
    WTF_CSRF_TIME_LIMIT = 3600 # CSRF token expiry in seconds (1 hour)
    WTF_CSRF_SSL_STRICT = False  # Set to True in production with HTTPS (requires HTTPS)
    
    # Application-wide Rate Limiting Configuration (e.g., using Flask-Limiter)
    RATELIMIT_STORAGE_URL = REDIS_URL # Use Redis for rate limit storage
    RATELIMIT_DEFAULT = "100 per hour" # Default rate limit for all routes
    RATELIMIT_HEADERS_ENABLED = True # Include rate limit headers in responses
    
    # Application URLs
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000') # Base URL of the backend application
    FRONTEND_URL = os.getenv('FRONTEND_URL', APP_URL) # Base URL of the frontend (if separate)
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO') # Default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_FILE = os.getenv('LOG_FILE', 'logs/nuddee_saas.log') # Main log file path
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB per log file
    LOG_BACKUP_COUNT = 10 # Number of backup log files to keep
    
    # Monitoring Configuration (for error tracking and performance monitoring)
    SENTRY_DSN = os.getenv('SENTRY_DSN') # Sentry Data Source Name
    NEW_RELIC_LICENSE_KEY = os.getenv('NEW_RELIC_LICENSE_KEY') # New Relic license key
    
    # Business Logic Configuration
    TRIAL_PERIOD_DAYS = 14 # Number of days for the free trial period
    MAX_FAILED_LOGIN_ATTEMPTS = 5 # Max failed login attempts before lockout
    ACCOUNT_LOCKOUT_DURATION = timedelta(minutes=30) # Duration of account lockout after too many failed attempts
    PASSWORD_RESET_EXPIRY = timedelta(hours=1) # Password reset token expiry
    
    # Feature Flags (can be controlled via environment variables)
    ENABLE_2FA = os.getenv('ENABLE_2FA', 'True').lower() == 'true' # Enable Two-Factor Authentication
    ENABLE_EMAIL_VERIFICATION = os.getenv('ENABLE_EMAIL_VERIFICATION', 'True').lower() == 'true' # Enable email verification on registration
    ENABLE_AUDIT_LOGGING = os.getenv('ENABLE_AUDIT_LOGGING', 'True').lower() == 'true' # Enable detailed audit logging
    ENABLE_ANALYTICS = os.getenv('ENABLE_ANALYTICS', 'False').lower() == 'true' # Enable analytics tracking
    
    # API Configuration
    API_RATE_LIMIT = "1000 per hour" # Default rate limit for API endpoints
    API_VERSION = "v1" # Current API version
    
    # Backup Configuration
    BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'True').lower() == 'true' # Enable automated backups
    BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', 24)) # How often to run backups
    BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', 30)) # How long to retain backups
    BACKUP_STORAGE_PATH = os.getenv('BACKUP_STORAGE_PATH', 'backups/') # Local path for backups
    
    @staticmethod
    def init_app(app):
        """
        Initialize application with configuration.
        This method should be called from the main Flask app.
        """
        # Create necessary directories if they don't exist
        directories = [
            Config.UPLOAD_FOLDER,
            'logs', # For general application logs
            'backups/teamup', # For TeamUp specific backups
            'backups/database', # For database backups
            'temp' # Temporary files
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True) # exist_ok=True prevents error if dir already exists
        
        # Validate required environment variables for production
        Config.validate_config()
        
        if app:
            # Configure logging for the Flask app instance
            Config.setup_logging(app)
            
            # Configure error tracking if Sentry DSN is provided
            if Config.SENTRY_DSN:
                Config.setup_sentry(app)
    
    @staticmethod
    def validate_config():
        """
        Validate critical configuration variables, especially for production.
        Raises ValueError if required variables are missing or insecure.
        """
        required_vars = []
        
        if not Config.MASTER_TEAMUP_API:
            required_vars.append('MASTER_TEAMUP_API')
        
        # Ensure SECRET_KEY is set and not the default placeholder
        if not Config.SECRET_KEY or Config.SECRET_KEY == 'your-super-secret-key-change-this-in-production':
            required_vars.append('SECRET_KEY')
        
        if required_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(required_vars)}")
        
        # Additional production-specific validations
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
            
            # Validate secret key strength in production
            secret_key = os.getenv('SECRET_KEY')
            if len(secret_key) < 32: # A strong secret key should be at least 32 characters
                raise ValueError("SECRET_KEY must be at least 32 characters long in production")
            
            # Validate database URL for production (discourage SQLite)
            database_url = os.getenv('DATABASE_URL')
            if database_url and database_url.startswith('sqlite'):
                raise ValueError("SQLite is not recommended for production. Use PostgreSQL or MySQL.")
    
    @staticmethod
    def setup_logging(app):
        """
        Setup application logging handlers.
        This function configures file-based logging for general info, errors, and security.
        """
        if not app.debug and not app.testing:
            # Ensure log directory exists
            log_dir = os.path.dirname(Config.LOG_FILE)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            # Add RequestInfoFilter to the root logger (or specific loggers)
            # This filter needs to be added before any handlers are added to ensure it processes all records
            if not any(isinstance(f, RequestInfoFilter) for f in app.logger.filters):
                app.logger.addFilter(RequestInfoFilter())
            
            # Prevent adding duplicate handlers if setup_logging is called multiple times
            if not app.logger.handlers:
                # Main application log handler
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
                
                # Error log handler (more detailed for errors)
                error_handler = RotatingFileHandler(
                    'logs/nuddee_errors.log', # Separate file for errors
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=5
                )
                # Custom formatter for errors to include request context
                error_formatter = logging.Formatter(
                    '%(asctime)s %(levelname)s: %(message)s\n'
                    'URL: %(url)s (%(method)s)\n' # Now uses injected 'url' and 'method'
                    'User: %(user_id)s\n' # Now uses injected 'user_id'
                    'IP: %(ip_address)s\n' # Now uses injected 'ip_address'
                    'User-Agent: %(user_agent)s\n' # Now uses injected 'user_agent'
                    'Traceback:\n%(traceback)s\n' + '='*80 # Now uses injected 'traceback'
                )
                error_handler.setFormatter(error_formatter)
                error_handler.setLevel(logging.ERROR)
                app.logger.addHandler(error_handler)

                # Security log handler
                security_handler = RotatingFileHandler(
                    'logs/nuddee_security.log', # Separate file for security events
                    maxBytes=Config.LOG_MAX_SIZE,
                    backupCount=10
                )
                security_handler.setFormatter(logging.Formatter(
                    '%(asctime)s SECURITY: %(message)s'
                ))
                security_handler.setLevel(logging.WARNING)
                
                # Create a dedicated security logger and add its handler
                security_logger = logging.getLogger('security')
                security_logger.addHandler(security_handler)
                security_logger.setLevel(logging.WARNING) # Security events are typically WARNING or higher

            app.logger.setLevel(getattr(logging, Config.LOG_LEVEL)) # Set overall app logger level
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
                traces_sample_rate=0.1, # Sample 10% of transactions for performance monitoring
                environment=os.getenv('FLASK_ENV', 'production') # Set environment in Sentry
            )
            app.logger.info("Sentry error tracking initialized.")
        except ImportError:
            app.logger.warning("Sentry SDK not installed, skipping error tracking setup.")
        except Exception as e:
            app.logger.error(f"Failed to initialize Sentry: {e}")

class DevelopmentConfig(Config):
    """Development configuration: Enables debug, relaxes security, logs SQL."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///nuddee_dev.db')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'echo': True  # Log SQL queries in development for debugging
    }
    
    # Disable CSRF for development convenience (DO NOT DO IN PRODUCTION)
    WTF_CSRF_ENABLED = False
    
    # Relaxed session security for development (DO NOT DO IN PRODUCTION)
    SESSION_COOKIE_SECURE = False
    
    # Enable debug toolbar for Flask
    DEBUG_TB_ENABLED = True
    DEBUG_TB_INTERCEPT_REDIRECTS = False
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app) # Call base class init_app
        
        # Setup Flask-DebugToolbar
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
    """Production configuration: Disables debug, enforces security, uses PostgreSQL, enables monitoring."""
    DEBUG = False
    
    # Use PostgreSQL in production (database URL must be provided via env var)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
    # Enable all security features for production
    SESSION_COOKIE_SECURE = True # Require HTTPS for session cookies
    WTF_CSRF_SSL_STRICT = True # Enforce strict CSRF checks over SSL
    
    # Production rate limits (more restrictive)
    RATELIMIT_DEFAULT = "60 per hour"
    API_RATE_LIMIT = "500 per hour"
    
    # Enable monitoring in production
    ENABLE_ANALYTICS = True
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app) # Call base class init_app
        
        # Setup production monitoring (New Relic)
        if cls.NEW_RELIC_LICENSE_KEY:
            try:
                import newrelic.agent
                newrelic.agent.initialize() # Initialize New Relic agent
                app.logger.info("New Relic monitoring initialized.")
            except ImportError:
                app.logger.warning("New Relic agent not installed, skipping monitoring setup.")
            except Exception as e:
                app.logger.error(f"Failed to initialize New Relic: {e}")
        
        # Log to syslog in production for centralized logging
        import logging
        from logging.handlers import SysLogHandler
        try:
            syslog_handler = SysLogHandler() # Default to /dev/log or /var/run/syslog
            syslog_handler.setLevel(logging.WARNING) # Only send WARNING and above to syslog
            app.logger.addHandler(syslog_handler)
            app.logger.info("Syslog handler added for production logging.")
        except Exception as e:
            app.logger.error(f"Failed to setup SysLogHandler: {e}")

class TestingConfig(Config):
    """Testing configuration: Uses in-memory SQLite, disables external services, faster hashing."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # In-memory database for fast tests
    WTF_CSRF_ENABLED = False # Disable CSRF for easier testing
    
    # Disable external services to avoid real calls during tests
    MAIL_SUPPRESS_SEND = True
    STRIPE_SECRET_KEY = 'sk_test_fake_key' # Use a fake key for tests
    MASTER_TEAMUP_API = 'test_api_key' # Use a test API key
    
    # Fast password hashing for quicker test execution
    # BCRYPT_LOG_ROUNDS = 4 # If using Flask-Bcrypt, lower rounds for speed
    
    # Shorter timeouts for tests to speed up failure detection
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=1)
    PASSWORD_RESET_EXPIRY = timedelta(minutes=1)

class StagingConfig(ProductionConfig):
    """Staging configuration: Similar to production but with debug features and relaxed limits."""
    DEBUG = True # Enable debug for easier debugging on staging
    
    # Use staging database (database URL must be provided via env var)
    SQLALCHEMY_DATABASE_URI = os.getenv('STAGING_DATABASE_URL')
    
    # More relaxed rate limits for staging than production
    RATELIMIT_DEFAULT = "200 per hour"
    
    # Enable debug toolbar on staging
    DEBUG_TB_ENABLED = True
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app) # Call base class init_app (ProductionConfig's init_app)
        # Setup Flask-DebugToolbar for staging
        try:
            from flask_debugtoolbar import DebugToolbarExtension
            toolbar = DebugToolbarExtension()
            toolbar.init_app(app)
            app.logger.info("Flask-DebugToolbar initialized for staging.")
        except ImportError:
            app.logger.warning("Flask-DebugToolbar not installed, skipping debug toolbar setup for staging.")
        except Exception as e:
            app.logger.error(f"Failed to initialize Flask-DebugToolbar for staging: {e}")

# Configuration dictionary to select config based on FLASK_ENV
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'default': DevelopmentConfig # Default to development if FLASK_ENV is not set
}

def get_config():
    """Get the appropriate configuration class based on the FLASK_ENV environment variable."""
    env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, config['default'])

# Environment-specific settings loader (can load .env.<env_name> files)
def load_environment_config():
    """
    Load additional environment-specific configuration from a .env.<env> file.
    This allows for environment-specific overrides of .env defaults.
    """
    env = os.getenv('FLASK_ENV', 'development')
    
    # Load environment-specific .env file (e.g., .env.production, .env.development)
    env_file = f'.env.{env}'
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True) # override=True allows values in env_file to override existing ones
    
    return get_config()

# Configuration validation (can be called at application startup)
def validate_production_config():
    """
    Validate critical production configuration variables.
    This is a separate function that can be called explicitly, e.g., during deployment.
    """
    if os.getenv('FLASK_ENV') == 'production':
        required_vars = [
            'SECRET_KEY',
            'DATABASE_URL',
            'REDIS_URL',
            'MASTER_TEAMUP_API',
            'STRIPE_SECRET_KEY',
            'MAIL_USERNAME',
            'MAIL_PASSWORD'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required production environment variables: {', '.join(missing_vars)}")
        
        # Validate secret key strength
        secret_key = os.getenv('SECRET_KEY')
        if len(secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long in production")
        
        # Validate database URL (ensure it's not SQLite in production)
        database_url = os.getenv('DATABASE_URL')
        if database_url and database_url.startswith('sqlite'):
            raise ValueError("SQLite is not recommended for production. Use PostgreSQL or MySQL.")

# Export commonly used config values (utility function)
def get_config_value(key, default=None):
    """Get a configuration value from the currently active config class with a fallback default."""
    config_class = get_config()
    return getattr(config_class, key, default)

# Health check configuration (for monitoring and readiness probes)
HEALTH_CHECK_CONFIG = {
    'database': True, # Check database connectivity
    'redis': True, # Check Redis connectivity
    'teamup_api': True, # Check TeamUp API connectivity
    'stripe_api': False,  # Don't check Stripe in health checks to avoid rate limits and unnecessary calls
    'mail_server': False, # Don't check mail server to avoid authentication issues and rate limits
}