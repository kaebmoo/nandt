#!/usr/bin/env python3
# run.py - Application entry point

import os
from app import app
from config import Config

if __name__ == '__main__':
    # Initialize configuration
    Config.init_app(app)
    
    # Run the application
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
    
    app.run(host='0.0.0.0', port=port, debug=debug)