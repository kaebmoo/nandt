#!/usr/bin/env python3
# run.py - Enhanced Development Server

import os
import sys
from app import app
from config import get_config

def main():
    """Main entry point for development server"""
    # Get configuration
    config_class = get_config()
    
    # Initialize configuration
    try:
        config_class.init_app(app)
        print(f"✅ Configuration loaded: {config_class.__name__}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    
    # Development server settings
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't')
    
    print(f"🚀 Starting NudDee SaaS Development Server")
    print(f"   Environment: {os.getenv('FLASK_ENV', 'development')}")
    print(f"   Debug Mode: {debug}")
    print(f"   URL: http://{host}:{port}")
    print(f"   Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        app.run(
            host=host, 
            port=port, 
            debug=debug,
            use_reloader=True,
            use_debugger=True,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()