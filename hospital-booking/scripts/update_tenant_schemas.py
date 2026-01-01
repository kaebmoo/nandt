import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from shared_db.database import engine

def update_tenant_schemas_raw():
    """
    Directly create the audit_logs table using raw SQL
    """
    print("Starting tenant schema update (Raw SQL)...")
    
    create_table_sql = """
    CREATE TABLE IF NOT exists audit_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        action VARCHAR(50) NOT NULL,
        resource_type VARCHAR(50),
        resource_id VARCHAR(50),
        details JSON,
        ip_address VARCHAR(45),
        user_agent VARCHAR(255),
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
    );
    """
    
    with engine.connect() as connection:
        connection.execute(text("SET search_path TO public"))
        result = connection.execute(text("SELECT schema_name, subdomain FROM hospitals WHERE status != 'deleted'"))
        tenants = result.fetchall()
        
        print(f"Found {len(tenants)} active tenants.")
        
        for schema_name, subdomain in tenants:
            print(f"Updating schema: {schema_name} ({subdomain})...")
            try:
                # Set search path
                connection.execute(text(f'SET search_path TO "{schema_name}"'))
                # Create table
                connection.execute(text(create_table_sql))
                connection.commit() # Important!
                print(f"  - OK (Table ensure created)")
            except Exception as e:
                print(f"  - Error updating {schema_name}: {e}")
                
    print("Update complete.")

if __name__ == "__main__":
    update_tenant_schemas_raw()
