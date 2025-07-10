#!/usr/bin/env python3
# setup.py - System Setup and Configuration Script

import os
import sys
import secrets
import click
from dotenv import load_dotenv
import requests
from pathlib import Path

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")

def print_info(message):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

def print_header(message):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"{message}")
    print(f"{'='*60}{Colors.END}\n")

@click.group()
def cli():
    """NudDee SaaS Setup and Configuration Tool"""
    pass

@cli.command()
def init():
    """Initialize the application with basic configuration"""
    print_header("NudDee SaaS Initialization")
    
    # Check if .env exists
    if os.path.exists('.env'):
        if not click.confirm('⚠️  .env file already exists. Overwrite?'):
            print_info("Setup cancelled.")
            return
    
    # Create .env from template
    if os.path.exists('.env.example'):
        import shutil
        shutil.copy('.env.example', '.env')
        print_success(".env file created from template")
    else:
        create_basic_env()
        print_success(".env file created with basic configuration")
    
    # Generate secret key
    secret_key = secrets.token_hex(32)
    update_env_var('SECRET_KEY', secret_key)
    print_success("Secret key generated")
    
    # Create necessary directories
    create_directories()
    
    print_success("Basic initialization completed!")
    print_info("Next steps:")
    print("  1. Edit .env file with your configuration")
    print("  2. Run: python setup.py check-config")
    print("  3. Run: python setup.py check-teamup")
    print("  4. Run: python manage.py db init")

def create_basic_env():
    """Create a basic .env file"""
    env_content = """# Basic NudDee SaaS Configuration
FLASK_ENV=development
SECRET_KEY=will-be-generated
DATABASE_URL=sqlite:///nuddee_saas.db
REDIS_URL=redis://localhost:6379/0

# TeamUp Configuration - REQUIRED
MASTER_TEAMUP_API=your-master-teamup-api-key-here
TEMPLATE_CALENDAR_KEY=your-template-calendar-key-here
TEAMUP_PLAN=free

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# Application URLs
APP_URL=http://localhost:5000
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)

def create_directories():
    """Create necessary directories"""
    directories = [
        'logs',
        'uploads',
        'backups/teamup',
        'backups/database',
        'temp'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print_success(f"Directory created: {directory}")

def update_env_var(key, value):
    """Update environment variable in .env file"""
    if not os.path.exists('.env'):
        return False
    
    lines = []
    found = False
    
    with open('.env', 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if line.startswith(f'{key}='):
            lines[i] = f'{key}={value}\n'
            found = True
            break
    
    if not found:
        lines.append(f'{key}={value}\n')
    
    with open('.env', 'w') as f:
        f.writelines(lines)
    
    return True

@cli.command()
def check_config():
    """Check configuration and dependencies"""
    print_header("Configuration Check")
    
    # Load environment variables
    load_dotenv()
    
    # Check required environment variables
    required_vars = {
        'SECRET_KEY': 'Secret key for Flask sessions',
        'DATABASE_URL': 'Database connection URL',
        'MASTER_TEAMUP_API': 'TeamUp master API key',
        'TEMPLATE_CALENDAR_KEY': 'TeamUp template calendar key'
    }
    
    all_good = True
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value and value != f'your-{var.lower().replace("_", "-")}-here':
            print_success(f"{var}: Configured")
        else:
            print_error(f"{var}: Missing or using placeholder")
            print_info(f"  Description: {description}")
            all_good = False
    
    # Check optional variables
    optional_vars = {
        'STRIPE_SECRET_KEY': 'Required for payment processing',
        'MAIL_USERNAME': 'Required for sending emails',
        'REDIS_URL': 'Required for caching and sessions'
    }
    
    print("\nOptional Configuration:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value and not value.startswith('your-'):
            print_success(f"{var}: Configured")
        else:
            print_warning(f"{var}: Not configured")
            print_info(f"  Description: {description}")
    
    # Check SECRET_KEY strength
    secret_key = os.getenv('SECRET_KEY')
    if secret_key and len(secret_key) >= 32:
        print_success("SECRET_KEY: Strong (32+ characters)")
    else:
        print_error("SECRET_KEY: Weak (less than 32 characters)")
        all_good = False
    
    if all_good:
        print_success("\n🎉 All required configuration is set!")
    else:
        print_error("\n❌ Please fix the configuration issues above.")

@cli.command()
def check_teamup():
    """Check TeamUp API configuration and connectivity"""
    print_header("TeamUp API Check")
    
    load_dotenv()
    
    master_api = os.getenv('MASTER_TEAMUP_API')
    template_key = os.getenv('TEMPLATE_CALENDAR_KEY')
    
    if not master_api or master_api == 'your-master-teamup-api-key-here':
        print_error("MASTER_TEAMUP_API not configured")
        print_info("Get your API key from: https://teamup.com/api-keys/")
        return
    
    if not template_key or template_key == 'your-template-calendar-key-here':
        print_error("TEMPLATE_CALENDAR_KEY not configured")
        print_info("Create a template calendar and copy its key (ksXXXXXXXX)")
        return
    
    # Test API connectivity
    headers = {
        'Accept': 'application/json',
        'Teamup-Token': master_api
    }
    
    try:
        print_info("Testing API connectivity...")
        
        # Test basic API access
        response = requests.get(
            "https://api.teamup.com/",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            print_success("TeamUp API: Connected")
        else:
            print_error(f"TeamUp API: Connection failed (Status: {response.status_code})")
            return
        
        # Test template calendar access
        print_info("Testing template calendar access...")
        
        response = requests.get(
            f"https://api.teamup.com/{template_key}/configuration",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            config_data = response.json()
            calendar_name = config_data.get('name', 'Unknown')
            print_success(f"Template calendar: Accessible ({calendar_name})")
            
            # Test copy capability
            print_info("Testing calendar copy capability...")
            
            test_copy_data = {
                'title': 'Test Copy - Can Delete',
                'copySubcalendars': True,
                'copyEvents': False
            }
            
            copy_response = requests.post(
                f"https://api.teamup.com/{template_key}/copy",
                headers=headers,
                json=test_copy_data,
                allow_redirects=False,
                timeout=30
            )
            
            if copy_response.status_code == 302:
                print_success("Calendar copy: Working")
                
                # Try to get the new calendar ID from redirect
                redirect_url = copy_response.headers.get('Location')
                if redirect_url:
                    import re
                    match = re.search(r'teamup\.com/(ks[a-zA-Z0-9]+)', redirect_url)
                    if match:
                        new_calendar_id = match.group(1)
                        print_info(f"Created test calendar: {new_calendar_id}")
                        print_warning("Please delete this test calendar from your TeamUp account")
            else:
                print_error(f"Calendar copy: Failed (Status: {copy_response.status_code})")
                print_info("Response: " + copy_response.text[:200])
                
        elif response.status_code == 403:
            print_error("Template calendar: No permission")
            print_info("Make sure MASTER_TEAMUP_API has admin access to the template calendar")
        elif response.status_code == 404:
            print_error("Template calendar: Not found")
            print_info("Check if TEMPLATE_CALENDAR_KEY is correct")
        else:
            print_error(f"Template calendar: Access failed (Status: {response.status_code})")
    
    except requests.exceptions.Timeout:
        print_error("TeamUp API: Timeout (check internet connection)")
    except requests.exceptions.ConnectionError:
        print_error("TeamUp API: Connection error (check internet connection)")
    except Exception as e:
        print_error(f"TeamUp API: Unexpected error - {str(e)}")

@cli.command()
def check_dependencies():
    """Check if all required dependencies are installed"""
    print_header("Dependencies Check")
    
    required_packages = [
        'flask',
        'flask-sqlalchemy',
        'flask-login',
        'flask-wtf',
        'werkzeug',
        'requests',
        'python-dotenv',
        'pyotp',
        'qrcode',
        'stripe'
    ]
    
    all_good = True
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package}: Installed")
        except ImportError:
            print_error(f"{package}: Not installed")
            all_good = False
    
    if not all_good:
        print_error("\nSome dependencies are missing. Install them with:")
        print("pip install -r requirements.txt")
    else:
        print_success("\n🎉 All dependencies are installed!")

@cli.command()
def generate_secret():
    """Generate a new secret key"""
    secret_key = secrets.token_hex(32)
    
    if os.path.exists('.env'):
        update_env_var('SECRET_KEY', secret_key)
        print_success("Secret key updated in .env file")
    else:
        print_info(f"Generated secret key: {secret_key}")
        print_warning("No .env file found. Copy the key above to your .env file.")

@cli.command()
@click.option('--org-name', prompt='Organization name')
@click.option('--admin-email', prompt='Admin email')
@click.option('--admin-password', prompt='Admin password', hide_input=True)
def create_demo():
    """Create demo organization and user"""
    print_header("Creating Demo Data")
    
    # This would need to import and use the actual models
    print_info("Demo creation would set up:")
    print(f"  - Organization: {org_name}")
    print(f"  - Admin user: {admin_email}")
    print("  - Sample subcalendars")
    print("  - Test appointments")
    
    print_warning("This command needs to be implemented with actual database operations")

@cli.command()
def doctor():
    """Run comprehensive system diagnostics"""
    print_header("System Diagnostics")
    
    print("🔍 Running comprehensive checks...")
    
    # Check configuration
    print("\n" + "="*40)
    print("Configuration Check")
    print("="*40)
    ctx = click.Context(check_config)
    ctx.invoke(check_config)
    
    # Check dependencies
    print("\n" + "="*40)
    print("Dependencies Check")
    print("="*40)
    ctx = click.Context(check_dependencies)
    ctx.invoke(check_dependencies)
    
    # Check TeamUp
    print("\n" + "="*40)
    print("TeamUp API Check")
    print("="*40)
    ctx = click.Context(check_teamup)
    ctx.invoke(check_teamup)
    
    # Check directories
    print("\n" + "="*40)
    print("Directory Check")
    print("="*40)
    
    directories = ['logs', 'uploads', 'backups', 'temp']
    for directory in directories:
        if os.path.exists(directory):
            print_success(f"Directory exists: {directory}")
        else:
            print_warning(f"Directory missing: {directory}")
    
    print_info("\n🏥 System diagnostics completed!")

if __name__ == '__main__':
    cli()