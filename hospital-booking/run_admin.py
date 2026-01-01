#!/usr/bin/env python3
"""
Entry point for Super Admin Flask Application
Runs the tenant management system on a separate port
"""

from admin_app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Run on different port (5002) to avoid conflict with main Flask app
    port = int(os.environ.get('ADMIN_PORT', 5002))
    host = os.environ.get('ADMIN_HOST', '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development' or os.environ.get('DEBUG', 'True').lower() == 'true'

    print("=" * 60)
    print("🏥 Hospital Booking - Super Admin Panel")
    print("=" * 60)
    print(f"📍 Running on: http://{host}:{port}")
    print(f"🔧 Debug mode: {debug}")
    print("=" * 60)
    print("\n⚠️  Note: This is the SUPER ADMIN panel")
    print("   Only super admin users can access this application")
    print("=" * 60)

    app.run(
        debug=debug,
        port=port,
        host=host
    )
