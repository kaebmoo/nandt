import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from shared_db.database import engine
from shared_db.models import Appointment

def check_appointments(schema_name):
    print(f"Checking appointments in schema: {schema_name}")
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # Raw SQL check
        result = connection.execute(text("SELECT id, booking_reference, guest_email FROM appointments"))
        rows = result.fetchall()
        print(f"Found {len(rows)} appointments (Raw SQL):")
        for row in rows:
            print(f"  - ID: {row[0]}, Ref: {row[1]}, Email: {row[2]}")

if __name__ == "__main__":
    check_appointments("tenant_monnum")
