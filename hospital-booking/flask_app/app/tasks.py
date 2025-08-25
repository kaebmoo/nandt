# flask_app/app/tasks.py

from . import create_app # Import your app factory
from celery import shared_task
import requests
from sqlalchemy import text

from shared_db.database import SessionLocal
from shared_db.models import Hospital
from .services.holiday_service import HolidayFetcher
from datetime import datetime

# Helper to get FastAPI URL from environment within the task
def get_fastapi_url_task():
    import os
    return os.environ.get("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

@shared_task(name="tasks.sync_all_tenant_holidays")
def sync_all_tenant_holidays(year=None):
    """
    A Celery task to sync holidays for all active tenants.
    """
    if year is None:
        year = datetime.now().year

    flask_app = create_app()
    with flask_app.app_context():
        db = SessionLocal()
        try:
            # Query public schema for all tenants
            db.execute(text('SET search_path TO public'))
            active_tenants = db.query(Hospital).all()
            
            if not active_tenants:
                print("No active tenants found to sync.")
                return

            print(f"Found {len(active_tenants)} tenants to sync for year {year}.")

            # Fetch holidays once
            holidays_to_sync = HolidayFetcher.fetch_holidays_from_ical(year)
            if not holidays_to_sync:
                print(f"Could not fetch holidays for year {year}. Aborting sync.")
                return
            
            # Convert dates to strings for JSON
            for h in holidays_to_sync:
                h['date'] = h['date'].isoformat()
            
            payload = {"year": year, "holidays": holidays_to_sync}
            
            # Loop through tenants and call their FastAPI endpoint
            for tenant in active_tenants:
                print(f"Syncing for tenant: {tenant.subdomain}...")
                url = f"{get_fastapi_url_task()}/api/v1/tenants/{tenant.subdomain}/holidays/sync"
                try:
                    response = requests.post(url, json=payload, timeout=20)
                    if response.status_code == 200:
                        print(f" -> Success for {tenant.subdomain}: {response.json().get('message')}")
                    else:
                        print(f" -> Failed for {tenant.subdomain}: {response.status_code} - {response.text}")
                except requests.RequestException as e:
                    print(f" -> API call failed for {tenant.subdomain}: {e}")
        
        finally:
            db.close()
    return "Holiday sync task finished."