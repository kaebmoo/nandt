import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from shared_db.database import engine, SessionLocal
from shared_db.models import Appointment

def check_humnoi_appointment():
    print("Checking Appointment 34 in tenant_humnoi...")
    
    # 1. Raw SQL Check
    with engine.connect() as connection:
        connection.execute(text('SET search_path TO "tenant_humnoi", public'))
        result = connection.execute(text("SELECT id, booking_reference, guest_email FROM appointments WHERE id = 34"))
        row = result.fetchone()
        if row:
            print(f"RAW SQL: Found - ID: {row[0]}, Email: {row[2]}")
        else:
            print("RAW SQL: Not Found")

    # 2. ORM Check
    db = SessionLocal()
    try:
        db.execute(text('SET search_path TO "tenant_humnoi", public'))
        visit = db.query(Appointment).filter_by(id=34).first()
        if visit:
             print(f"ORM: Found - ID: {visit.id}, Email: {visit.guest_email}")
        else:
             print("ORM: Not Found")
    finally:
        db.close()

if __name__ == "__main__":
    check_humnoi_appointment()
