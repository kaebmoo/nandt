# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

This is a multi-tenanted hospital booking system with a **hybrid architecture**:

- **Flask App** (`flask_app/`): Main web application for hospital admin dashboards and public booking pages
- **FastAPI App** (`fastapi_app/`): API-only service for event types, availability, bookings, and holidays
- **Shared Database** (`shared_db/`): Common database models and connection logic
- **Multi-tenancy**: PostgreSQL schemas - `public` schema for hospitals/users, tenant-specific schemas for booking data

### Key Components

**Database Architecture:**
- Public schema: `Hospital`, `User` models for multi-tenant management  
- Tenant schemas: `AvailabilityTemplate`, `EventType`, `Provider`, `Patient`, `Booking` models
- Each hospital gets its own schema (e.g., `tenant_humnoi`)

**URL Routing:**
- Development: `localhost/dashboard?subdomain=humnoi` 
- Production: `humnoi.yourdomain.com/dashboard`
- Universal URL generation handles both modes automatically

## Development Commands

### Running the Applications

```bash
# Start Flask app (port 5001)
cd flask_app && python run.py

# Start FastAPI app (port 8000) 
cd fastapi_app && uvicorn app.main:app --reload --port 8000

# Start background worker (Redis/RQ)
python worker.py
```

### Database Operations

```bash
# Run database migrations
cd migrations && python <migration_script>.py

# Debug database connections
cd migrations && python debug_database.py
```

### Configuration

The application uses `.env` file for configuration. Key environment variables:
- `DATABASE_URL`: PostgreSQL connection
- `REDIS_URL`: Redis for background tasks
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`: Payment processing
- `ENVIRONMENT`: "development" or "production" 
- `DOMAIN`: Base domain for URL generation

## Coding Patterns

### Database Sessions
Always use the established session management:
```python
# In Flask routes
from flask import g
db = g.db  # Set up by before_request middleware

# In FastAPI
from shared_db.database import SessionLocal
db = SessionLocal()
```

### Multi-tenant Database Access
```python
# Tenant schema is automatically set by middleware
# Use text() wrapper for all SQL commands:
from sqlalchemy import text
db.execute(text('SET search_path TO "tenant_schema", public'))
```

### URL Generation
Always use helper functions instead of `url_for` directly:
```python
# In Python routes
from .utils.url_helper import build_url_with_context
return redirect(build_url_with_context('main.dashboard'))

# In templates  
{{ nav_url('main.dashboard') }}  # Not url_for()
```

### API Integration
FastAPI service calls from Flask:
```python
def get_fastapi_url():
    return os.environ.get('FASTAPI_BASE_URL', 'http://127.0.0.1:8000')

# Use for availability, booking, event type operations
```

## File Structure

```
hospital-booking/
├── flask_app/           # Main web application
│   ├── app/
│   │   ├── __init__.py     # Flask app factory with multi-tenancy setup
│   │   ├── routes.py       # Main dashboard routes  
│   │   ├── auth.py         # Authentication
│   │   ├── public_booking.py # Public booking interface
│   │   ├── core/           # Core utilities
│   │   │   ├── tenant_manager.py
│   │   │   └── template_helpers.py
│   │   └── utils/          # Utility functions
│   │       ├── url_helper.py
│   │       └── security.py
│   └── run.py
├── fastapi_app/         # API service
│   └── app/
│       ├── main.py         # FastAPI app with universal URL generation
│       ├── booking.py      # Booking API endpoints
│       ├── availability.py # Availability management
│       ├── event_types.py  # Event type management
│       └── holidays.py     # Holiday management
├── shared_db/           # Database models and connections
│   ├── models.py           # SQLAlchemy models (PublicBase/TenantBase)
│   └── database.py         # Database connection setup
├── migrations/          # Database migration scripts
└── worker.py           # Redis/RQ background worker
```

## Common Tasks

### Adding New Routes
1. For admin features: Add to `flask_app/app/routes.py` or create new blueprint
2. For API features: Add to appropriate FastAPI router
3. Always use `build_url_with_context()` for redirects
4. Test both subdomain and query parameter URL modes

### Database Changes
1. Create migration script in `migrations/` directory
2. Test on both public and tenant schemas
3. Use `text()` wrapper for all raw SQL

### Multi-tenant Features
1. All tenant-specific data uses tenant schemas automatically
2. Check `g.tenant` for current tenant schema
3. Public data (hospitals, users) stays in public schema

### Testing
Test both URL modes:
- `http://localhost/dashboard?subdomain=hospital1`
- `http://hospital1.localhost/dashboard` (requires local DNS setup)

## Known Issues

- URL generation inconsistency (see `subdomain_fixed.md` for details)
- Some template filters are duplicated across files
- Error handling needs improvement in API integration points
- N+1 query issues in dashboard data loading

## Dependencies

Main Python packages:
- Flask with Blueprints, Sessions, Mail
- FastAPI with Pydantic models
- SQLAlchemy for database ORM
- Redis/RQ for background tasks
- Stripe for payment processing
- Celery for scheduled tasks (holiday sync)