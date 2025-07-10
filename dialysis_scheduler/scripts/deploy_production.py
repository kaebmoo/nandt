# scripts/deploy_production.py
"""
Production deployment script for Dialysis Scheduler
"""
import os
import sys
import subprocess
import logging
from pathlib import Path

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def check_environment():
    """ตรวจสอบ environment และ dependencies"""
    logger = logging.getLogger(__name__)
    
    # ตรวจสอบ Python version
    if sys.version_info < (3, 8):
        logger.error("Python 3.8+ is required")
        return False
    
    # ตรวจสอบไฟล์ที่จำเป็น
    required_files = [
        '.env',
        'app.py',
        'config.py',
        'requirements_production.txt'
    ]
    
    for file in required_files:
        if not Path(file).exists():
            logger.error(f"Required file not found: {file}")
            return False
    
    return True

def install_dependencies():
    """ติดตั้ง dependencies สำหรับ production"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Installing production dependencies...")
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 
            '-r', 'requirements_production.txt'
        ], check=True)
        logger.info("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False

def create_directories():
    """สร้างโฟลเดอร์ที่จำเป็น"""
    logger = logging.getLogger(__name__)
    
    directories = ['logs', 'uploads', 'instance']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        logger.info(f"Created directory: {directory}")

def validate_config():
    """ตรวจสอบ configuration"""
    logger = logging.getLogger(__name__)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    required_env_vars = [
        'SECRET_KEY',
        'TEAMUP_API',
        'CALENDAR_ID'
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        return False
    
    # ตรวจสอบ SECRET_KEY
    secret_key = os.getenv('SECRET_KEY')
    if secret_key == 'your-secret-key-change-in-production':
        logger.error("Please change SECRET_KEY in .env file")
        return False
    
    logger.info("Configuration validated successfully")
    return True

def set_permissions():
    """ตั้งค่า file permissions สำหรับ production"""
    logger = logging.getLogger(__name__)
    
    # ตั้งค่าความปลอดภัยของไฟล์
    os.chmod('.env', 0o600)  # รัดกุม
    os.chmod('logs', 0o755)
    os.chmod('uploads', 0o755)
    
    logger.info("File permissions set successfully")

def test_application():
    """ทดสอบ application"""
    logger = logging.getLogger(__name__)
    
    try:
        # Import และ test basic functionality
        from app import app
        
        with app.test_client() as client:
            response = client.get('/')
            if response.status_code == 200:
                logger.info("Application test passed")
                return True
            else:
                logger.error(f"Application test failed: {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"Application test failed: {e}")
        return False

def main():
    """Main deployment function"""
    logger = setup_logging()
    logger.info("Starting production deployment...")
    
    steps = [
        ("Checking environment", check_environment),
        ("Installing dependencies", install_dependencies),
        ("Creating directories", create_directories),
        ("Validating configuration", validate_config),
        ("Setting permissions", set_permissions),
        ("Testing application", test_application)
    ]
    
    for step_name, step_func in steps:
        logger.info(f"Step: {step_name}")
        if not step_func():
            logger.error(f"Deployment failed at step: {step_name}")
            sys.exit(1)
    
    logger.info("Production deployment completed successfully!")
    logger.info("You can now start the application with:")
    logger.info("gunicorn --bind 0.0.0.0:8000 --workers 4 app:app")

if __name__ == "__main__":
    main()
