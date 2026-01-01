import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text, inspect
from shared_db.database import engine

def check_tables(schema_name):
    print(f"Checking tables in schema: {schema_name}")
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}", public'))
        result = connection.execute(text(
            f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema_name}'"
        ))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables found: {tables}")
        
        if 'audit_logs' in tables:
            print("SUCCESS: audit_logs table exists.")
        else:
            print("FAILURE: audit_logs table MISSING.")

if __name__ == "__main__":
    check_tables("tenant_monnum")
