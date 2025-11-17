#!/usr/bin/env python3
"""Debug script to check provider schedules in database"""

import os
import sys
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'shared_db'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def debug_provider_schedules(schema_name):
    """Debug provider schedules for a specific tenant"""
    db = SessionLocal()
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))

        print(f"\n{'='*80}")
        print(f"Schema: {schema_name}")
        print(f"{'='*80}")

        # Get all provider schedules
        schedules = db.execute(text("""
            SELECT
                ps.id,
                ps.provider_id,
                p.name as provider_name,
                ps.template_id,
                ps.effective_date,
                ps.end_date,
                ps.days_of_week,
                ps.custom_start_time,
                ps.custom_end_time,
                ps.schedule_type,
                ps.is_active,
                ps.notes
            FROM provider_schedules ps
            JOIN providers p ON p.id = ps.provider_id
            ORDER BY ps.template_id, ps.provider_id
        """)).fetchall()

        print(f"\n📋 Found {len(schedules)} provider schedules:")
        print()

        for sched in schedules:
            print(f"ID: {sched.id}")
            print(f"  Provider: [{sched.provider_id}] {sched.provider_name}")
            print(f"  Template ID: {sched.template_id}")
            print(f"  Effective: {sched.effective_date}")
            print(f"  End Date: {sched.end_date}")
            print(f"  Days of Week: {sched.days_of_week} (type: {type(sched.days_of_week)})")
            print(f"  Custom Times: {sched.custom_start_time} - {sched.custom_end_time}")
            print(f"  Type: {sched.schedule_type}")
            print(f"  Active: {sched.is_active}")
            print(f"  Notes: {sched.notes}")
            print()

        # Check today's date and what day it is
        today = date.today()
        weekday = today.weekday()  # Python weekday (0=Monday)
        converted_day = 0 if weekday == 6 else weekday + 1  # Convert to DayOfWeek (0=Sunday)

        print(f"\n📅 Today's Info:")
        print(f"  Date: {today}")
        print(f"  Python Weekday: {weekday} (0=Monday)")
        print(f"  Converted Day: {converted_day} (0=Sunday)")
        print()

        # Test the matching logic
        print(f"\n🔍 Testing Match Logic for Today ({today}):")
        for sched in schedules:
            print(f"\nSchedule ID {sched.id} - {sched.provider_name}:")

            # Check effective date
            if sched.effective_date > today:
                print(f"  ❌ Not effective yet (starts {sched.effective_date})")
                continue

            # Check end date
            if sched.end_date and sched.end_date < today:
                print(f"  ❌ Expired (ended {sched.end_date})")
                continue

            # Check active status
            if not sched.is_active:
                print(f"  ❌ Not active")
                continue

            # Check days of week
            days = sched.days_of_week
            print(f"  Days stored: {days} (type: {type(days)})")

            if days is None:
                print(f"  ❌ days_of_week is NULL")
                continue

            # Try to check if converted_day is in days
            try:
                if isinstance(days, list):
                    if converted_day in days:
                        print(f"  ✅ Matches today (day {converted_day} in {days})")
                    else:
                        print(f"  ❌ Today ({converted_day}) not in schedule days {days}")
                elif isinstance(days, str):
                    # Might be stored as string, try to parse
                    import json
                    parsed_days = json.loads(days)
                    if converted_day in parsed_days:
                        print(f"  ✅ Matches today (day {converted_day} in {parsed_days})")
                    else:
                        print(f"  ❌ Today ({converted_day}) not in schedule days {parsed_days}")
                else:
                    print(f"  ⚠️  Unexpected type: {type(days)}")
            except Exception as e:
                print(f"  ❌ Error checking days: {e}")

    finally:
        db.close()


def get_tenants():
    """Get all tenant schemas"""
    db = SessionLocal()
    try:
        db.execute(text("SET search_path TO public"))
        result = db.execute(text("SELECT subdomain, schema_name FROM hospitals")).fetchall()
        return result
    finally:
        db.close()


def main():
    print("🔍 Debugging Provider Schedules")

    tenants = get_tenants()
    print(f"\n📋 Found {len(tenants)} tenants: {[t[0] for t in tenants]}")

    for subdomain, schema_name in tenants:
        try:
            debug_provider_schedules(schema_name)
        except Exception as e:
            print(f"\n❌ Error debugging {schema_name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
