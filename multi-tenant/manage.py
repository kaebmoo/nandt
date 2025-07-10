#!/usr/bin/env python3
# manage.py - CLI Management Commands

import click
import os
import sys
from flask import Flask
from flask.cli import with_appcontext

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, Organization, User, SubscriptionPlan, UserRole
from hybrid_teamup_strategy import HybridTeamUpManager, TeamUpMonitor, TeamUpBackup
import uuid

@click.group()
def cli():
    """NandT SaaS Management Commands"""
    pass

# Database Commands
@cli.group()
def db_cmd():
    """Database management commands"""
    pass

@db_cmd.command('init')
@with_appcontext
def init_db():
    """Initialize database tables"""
    try:
        db.create_all()
        click.echo("✅ Database tables created successfully")
    except Exception as e:
        click.echo(f"❌ Error creating database: {e}")

@db_cmd.command('reset')
@click.confirmation_option(prompt='Are you sure you want to reset the database?')
@with_appcontext
def reset_db():
    """Reset database (DROP ALL TABLES)"""
    try:
        db.drop_all()
        db.create_all()
        click.echo("✅ Database reset successfully")
    except Exception as e:
        click.echo(f"❌ Error resetting database: {e}")

@db_cmd.command('seed')
@with_appcontext
def seed_db():
    """Seed database with sample data"""
    try:
        # สร้าง sample organization
        from werkzeug.security import generate_password_hash
        from models import SubscriptionPlan, UserRole
        
        # Organization
        org = Organization(
            name="รพ.สต.ตัวอย่าง",
            contact_email="admin@example.com",
            phone="02-123-4567",
            address="123 ถนนตัวอย่าง กรุงเทพฯ"
        )
        db.session.add(org)
        db.session.flush()
        
        # Admin User
        admin = User(
            organization_id=org.id,
            email="admin@example.com",
            first_name="ผู้ดูแล",
            last_name="ระบบ",
            role=UserRole.ADMIN
        )
        admin.set_password("admin123")
        db.session.add(admin)
        
        # Staff User
        staff = User(
            organization_id=org.id,
            email="staff@example.com",
            first_name="เจ้าหน้าที่",
            last_name="ทดสอบ",
            role=UserRole.STAFF
        )
        staff.set_password("staff123")
        db.session.add(staff)
        
        db.session.commit()
        
        click.echo("✅ Sample data created:")
        click.echo(f"   Organization: {org.name}")
        click.echo(f"   Admin: admin@example.com / admin123")
        click.echo(f"   Staff: staff@example.com / staff123")
        
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Error seeding database: {e}")

# TeamUp Commands
@cli.group()
def teamup():
    """TeamUp management commands"""
    pass

@teamup.command('setup')
@click.argument('org_id')
@with_appcontext
def setup_org_teamup(org_id):
    """Setup TeamUp calendars for organization"""
    try:
        org = Organization.query.get(org_id)
        if not org:
            click.echo(f"❌ Organization not found: {org_id}")
            return
        
        manager = HybridTeamUpManager()
        result = manager.create_organization_setup(org)
        
        if result['success']:
            click.echo(f"✅ TeamUp setup created for {org.name}")
            click.echo(f"   Primary Calendar: {result['primary_calendar_id']}")
            click.echo(f"   Subcalendars: {len(result['subcalendars'])}")
        else:
            click.echo(f"❌ Setup failed: {result['error']}")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")

@teamup.command('usage')
@with_appcontext
def teamup_usage():
    """Show TeamUp usage report"""
    try:
        monitor = TeamUpMonitor()
        report = monitor.check_calendar_usage()
        
        click.echo("📊 TeamUp Usage Report")
        click.echo("=" * 50)
        click.echo(f"Total Calendars: {report['total_calendars']}")
        click.echo(f"Total Subcalendars: {report['total_subcalendars']}")
        
        if report['calendars_full']:
            click.echo(f"\n🔴 Full Calendars ({len(report['calendars_full'])}):")
            for cal in report['calendars_full']:
                click.echo(f"   • {cal['organization']}: {cal['count']}/8 subcalendars")
        
        if report['calendars_near_limit']:
            click.echo(f"\n🟡 Nearly Full Calendars ({len(report['calendars_near_limit'])}):")
            for cal in report['calendars_near_limit']:
                click.echo(f"   • {cal['organization']}: {cal['usage_percent']:.1f}% ({cal['count']}/8)")
        
        if not report['calendars_full'] and not report['calendars_near_limit']:
            click.echo("\n✅ All calendars are running smoothly!")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")

@teamup.command('sync')
@with_appcontext
def teamup_sync():
    """Sync data with TeamUp API"""
    try:
        monitor = TeamUpMonitor()
        results = monitor.sync_with_teamup()
        
        click.echo("🔄 TeamUp Sync Report")
        click.echo("=" * 50)
        
        synced = 0
        errors = 0
        
        for result in results:
            org_name = result['organization']
            status = result['status']
            
            if status == 'synced':
                click.echo(f"✅ {org_name}: Synced ({result.get('subcalendar_count', 0)} subcalendars)")
                synced += 1
            elif status == 'calendar_not_found':
                click.echo(f"❌ {org_name}: Calendar not found in TeamUp")
                errors += 1
            elif status == 'error':
                click.echo(f"💥 {org_name}: Error - {result.get('error', 'Unknown')}")
                errors += 1
        
        click.echo(f"\nSummary: {synced} synced, {errors} issues")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}")

@teamup.command('backup')
@click.argument('org_id')
@with_appcontext
def backup_org(org_id):
    """Backup organization's TeamUp data"""
    try:
        org = Organization.query.get(org_id)
        if not org:
            click.echo(f"❌ Organization not found: {org_id}")
            return
        
        backup = TeamUpBackup()
        result = backup.backup_organization_calendars(org_id)
        
        if result['success']:
            filepath = backup.save_backup_to_file(org_id, result['data'])
            click.echo(f"✅ Backup created for {org.name}")
            click.echo(f"   File: {filepath}")
            click.echo(f"   Calendars: {len(result['data']['calendars'])}")
            click.echo(f"   Events: {len(result['data']['events'])}")
        else:
            click.echo(f"❌ Backup failed: {result['error']}")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")

# User Commands
@cli.group()
def user():
    """User management commands"""
    pass

@user.command('list')
@with_appcontext
def list_users():
    """List all users"""
    try:
        users = User.query.join(Organization).all()
        
        click.echo("👥 Users List")
        click.echo("=" * 80)
        click.echo(f"{'Email':<30} {'Name':<25} {'Role':<10} {'Organization':<20}")
        click.echo("-" * 80)
        
        for user in users:
            click.echo(f"{user.email:<30} {user.get_full_name():<25} {user.role.value:<10} {user.organization.name:<20}")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")

@user.command('create')
@click.option('--email', prompt=True, help='User email')
@click.option('--password', prompt=True, hide_input=True, help='User password')
@click.option('--first-name', prompt=True, help='First name')
@click.option('--last-name', prompt=True, help='Last name')
@click.option('--org-id', prompt=True, help='Organization ID')
@click.option('--role', type=click.Choice(['admin', 'staff']), default='staff', help='User role')
@with_appcontext
def create_user(email, password, first_name, last_name, org_id, role):
    """Create a new user"""
    try:
        # Check if organization exists
        org = Organization.query.get(org_id)
        if not org:
            click.echo(f"❌ Organization not found: {org_id}")
            return
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            click.echo(f"❌ Email already exists: {email}")
            return
        
        from models import UserRole
        
        user = User(
            organization_id=org_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN if role == 'admin' else UserRole.STAFF
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        click.echo(f"✅ User created successfully")
        click.echo(f"   Email: {email}")
        click.echo(f"   Name: {first_name} {last_name}")
        click.echo(f"   Role: {role}")
        click.echo(f"   Organization: {org.name}")
        
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Error: {e}")

# Organization Commands
@cli.group()
def org():
    """Organization management commands"""
    pass

@org.command('list')
@with_appcontext
def list_orgs():
    """List all organizations"""
    try:
        orgs = Organization.query.all()
        
        click.echo("🏥 Organizations List")
        click.echo("=" * 100)
        click.echo(f"{'ID':<8} {'Name':<30} {'Plan':<10} {'Status':<12} {'Users':<6} {'Created':<12}")
        click.echo("-" * 100)
        
        for org in orgs:
            user_count = User.query.filter_by(organization_id=org.id).count()
            created = org.created_at.strftime('%Y-%m-%d') if org.created_at else 'N/A'
            
            click.echo(f"{org.id[:8]:<8} {org.name[:29]:<30} {org.subscription_plan.value:<10} {org.subscription_status.value:<12} {user_count:<6} {created:<12}")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")

@org.command('create')
@click.option('--name', prompt=True, help='Organization name')
@click.option('--email', prompt=True, help='Contact email')
@click.option('--phone', help='Phone number')
@click.option('--address', help='Address')
@with_appcontext
def create_org(name, email, phone, address):
    """Create a new organization"""
    try:
        org = Organization(
            name=name,
            contact_email=email,
            phone=phone or '',
            address=address or ''
        )
        
        db.session.add(org)
        db.session.commit()
        
        click.echo(f"✅ Organization created successfully")
        click.echo(f"   ID: {org.id}")
        click.echo(f"   Name: {org.name}")
        click.echo(f"   Email: {org.contact_email}")
        click.echo("\n💡 Next steps:")
        click.echo(f"   1. Setup TeamUp: python manage.py teamup setup {org.id}")
        click.echo(f"   2. Create admin user: python manage.py user create --org-id {org.id} --role admin")
        
    except Exception as e:
        db.session.rollback()
        click.echo(f"❌ Error: {e}")

# Development Commands
@cli.group()
def dev():
    """Development commands"""
    pass

@dev.command('run')
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def run_dev(host, port, debug):
    """Run development server"""
    click.echo(f"🚀 Starting NandT SaaS development server...")
    click.echo(f"   URL: http://{host}:{port}")
    click.echo(f"   Debug: {debug}")
    
    app.run(host=host, port=port, debug=debug)

@dev.command('check')
@with_appcontext
def check_config():
    """Check configuration"""
    click.echo("🔧 Configuration Check")
    click.echo("=" * 50)
    
    # Database
    try:
        db.engine.execute('SELECT 1')
        click.echo("✅ Database: Connected")
    except Exception as e:
        click.echo(f"❌ Database: {e}")
    
    # TeamUp API
    master_api = os.getenv('MASTER_TEAMUP_API')
    if master_api:
        click.echo("✅ TeamUp API: Key configured")
    else:
        click.echo("❌ TeamUp API: Key missing")
    
    # Stripe
    stripe_key = os.getenv('STRIPE_SECRET_KEY')
    if stripe_key:
        click.echo("✅ Stripe: Key configured")
    else:
        click.echo("❌ Stripe: Key missing")
    
    # Email
    mail_server = os.getenv('MAIL_SERVER')
    if mail_server:
        click.echo("✅ Email: Server configured")
    else:
        click.echo("❌ Email: Server missing")

# Add main function for command line usage
if __name__ == '__main__':
    cli()