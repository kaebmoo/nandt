# flask_app/app/tasks.py

from . import create_app # Import your app factory
from celery import shared_task
import requests
from sqlalchemy import text

from shared_db.database import SessionLocal, bind_tenant
from shared_db.models import Hospital, HospitalStatus
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
            bind_tenant(db, None)
            db.execute(text('SET search_path TO public'))
            active_tenants = (
                db.query(Hospital)
                .filter(Hospital.status == HospitalStatus.ACTIVE)
                .all()
            )
            
            if not active_tenants:
                print("No active tenants found to sync.")
                return

            print(f"Found {len(active_tenants)} tenants to sync for year {year}.")

            # ส่ง holidays ว่าง → FastAPI /holidays/sync จะ fetch จาก BOT API เอง
            # (mirror หน้า settings/holidays ที่ใช้งานได้จริง — holiday_routes.py:sync_holidays)
            # เดิมใช้ HolidayFetcher.fetch_holidays_from_ical ที่ไม่มีคลาสนี้อยู่จริง → import พัง
            payload = {"year": year, "holidays": []}

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
            bind_tenant(db, None)
            try:
                db.execute(text("SET search_path TO public"))
                db.commit()
            except Exception:
                db.rollback()
            db.close()
    return "Holiday sync task finished."


@shared_task(name="tasks.sync_all_tenant_sessions")
def sync_all_tenant_sessions(days_ahead=14):
    """Celery task รายวัน (1B.2): regenerate queue sessions ช่วง [today, today+days_ahead]
    ให้ทุก active service_point ที่ map template — ทุก tenant

    ต่างจาก holiday task: session generator เป็น pure service (พึ่งแค่ shared_db) จึง bind_tenant
    ตรง ๆ ต่อ tenant ได้ ไม่ต้องยิง HTTP เข้า FastAPI. ใช้ session แยกต่อ tenant (isolation +
    คืน connection สะอาด กัน search_path ค้างข้าม schema). idempotent + future-only โดย generator
    """
    from sqlalchemy import text
    from shared_db.models import Hospital, HospitalStatus
    from .services.session_service import sync_sessions_rolling

    # 1) ดึงรายชื่อ schema จาก public (ยังไม่ผูก tenant)
    db = SessionLocal()
    try:
        bind_tenant(db, None)
        db.execute(text("SET search_path TO public"))
        schemas = [
            h.schema_name
            for h in (
                db.query(Hospital)
                .filter(Hospital.status == HospitalStatus.ACTIVE)
                .all()
            )
        ]
    finally:
        bind_tenant(db, None)
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()

    # 2) sync ทีละ tenant ด้วย session ใหม่ (bind → run → คืน connection สะอาด)
    results = {}
    for schema in schemas:
        tdb = SessionLocal()
        try:
            bind_tenant(tdb, schema)
            tdb.execute(text(f'SET search_path TO "{schema}", public'))
            summary = sync_sessions_rolling(tdb, days_ahead=days_ahead)
            results[schema] = {
                'service_points': summary['service_points'],
                'sessions': summary['sessions'],
                'date_from': summary['date_from'].isoformat(),
                'date_to': summary['date_to'].isoformat(),
            }
            print(f"[session-sync] {schema}: {summary['service_points']} sp, "
                  f"{summary['sessions']} sessions")
        except Exception as e:
            results[schema] = {'error': str(e)}
            print(f"[session-sync] {schema} FAILED: {e}")
        finally:
            bind_tenant(tdb, None)
            try:
                tdb.execute(text("SET search_path TO public"))
                tdb.commit()
            except Exception:
                tdb.rollback()
            tdb.close()

    return results


@shared_task(name="tasks.sweep_all_tenant_no_shows")
def sweep_all_tenant_no_shows():
    """Celery task (Phase 2.5): mark checked_in entries past session/appointment close as no_show.

    ทำต่อ tenant เหมือน session sync: bind schema, run service, reset connection. queue_service
    เป็นคนรักษา state machine + append-only queue_events.
    """
    from shared_db.models import Hospital, HospitalStatus
    from .services.queue_service import sweep_no_shows

    db = SessionLocal()
    try:
        bind_tenant(db, None)
        db.execute(text("SET search_path TO public"))
        schemas = [
            h.schema_name
            for h in (
                db.query(Hospital)
                .filter(Hospital.status == HospitalStatus.ACTIVE)
                .all()
            )
        ]
    finally:
        bind_tenant(db, None)
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()

    results = {}
    for schema in schemas:
        tdb = SessionLocal()
        try:
            bind_tenant(tdb, schema)
            tdb.execute(text(f'SET search_path TO "{schema}", public'))
            marked = sweep_no_shows(tdb)
            results[schema] = {'no_show': marked}
            print(f"[no-show-sweep] {schema}: {marked} entries")
        except Exception as e:
            results[schema] = {'error': str(e)}
            print(f"[no-show-sweep] {schema} FAILED: {e}")
        finally:
            bind_tenant(tdb, None)
            try:
                tdb.execute(text("SET search_path TO public"))
                tdb.commit()
            except Exception:
                tdb.rollback()
            tdb.close()

    return results
