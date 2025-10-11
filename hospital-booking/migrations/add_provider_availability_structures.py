#!/usr/bin/env python3
"""Migration script to add provider scheduling and capacity structures.

Run from migrations directory:
    python add_provider_availability_structures.py
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv


load_dotenv()


ADD_TEMPLATE_COLUMNS_SQL = [
    """
    ALTER TABLE availability_templates
    ADD COLUMN IF NOT EXISTS template_type VARCHAR(20) DEFAULT 'dedicated'
    """,
    """
    ALTER TABLE availability_templates
    ADD COLUMN IF NOT EXISTS max_concurrent_slots INTEGER DEFAULT 1
    """,
    """
    ALTER TABLE availability_templates
    ADD COLUMN IF NOT EXISTS requires_provider_assignment BOOLEAN DEFAULT TRUE
    """,
]


CREATE_TEMPLATE_PROVIDERS_SQL = """
CREATE TABLE IF NOT EXISTS template_providers (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES availability_templates(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT FALSE,
    can_auto_assign BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_template_provider UNIQUE (template_id, provider_id)
);
"""


CREATE_PROVIDER_SCHEDULES_SQL = """
CREATE TABLE IF NOT EXISTS provider_schedules (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    template_id INTEGER NOT NULL REFERENCES availability_templates(id) ON DELETE CASCADE,
    effective_date DATE NOT NULL,
    end_date DATE,
    recurrence_pattern VARCHAR(50),
    days_of_week JSON,
    custom_start_time TIME,
    custom_end_time TIME,
    schedule_type VARCHAR(20) DEFAULT 'regular',
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_PROVIDER_SCHEDULES_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION provider_schedules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER provider_schedules_set_updated_at
BEFORE UPDATE ON provider_schedules
FOR EACH ROW
EXECUTE FUNCTION provider_schedules_updated_at();
"""


CREATE_RESOURCE_CAPACITIES_SQL = """
CREATE TABLE IF NOT EXISTS resource_capacities (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES availability_templates(id) ON DELETE CASCADE,
    specific_date DATE,
    day_of_week dayofweek,
    available_rooms INTEGER NOT NULL,
    max_concurrent_appointments INTEGER,
    time_slot_start TIME,
    time_slot_end TIME,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_PROVIDER_LEAVES_SQL = """
CREATE TABLE IF NOT EXISTS provider_leaves (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    leave_type VARCHAR(20),
    reason TEXT,
    approved_by VARCHAR(100),
    is_approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_INDEXES_SQL = [
    """
    CREATE INDEX IF NOT EXISTS ix_template_providers_template_id
    ON template_providers(template_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_template_providers_provider_id
    ON template_providers(provider_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_provider_schedules_provider_template
    ON provider_schedules(provider_id, template_id, effective_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_provider_leaves_provider
    ON provider_leaves(provider_id, start_date, end_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_resource_capacities_template
    ON resource_capacities(template_id, COALESCE(specific_date::timestamp, 'epoch'::timestamp))
    """,
]


def run_migration():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable is required")
        return False

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        tenants = session.execute(text("SELECT subdomain, schema_name FROM public.hospitals"))
        tenants = tenants.fetchall()

        if not tenants:
            print("⚠️  No tenant schemas found. Nothing to migrate.")
            return True

        print(f"👉 Found {len(tenants)} tenant schemas to migrate")

        for subdomain, schema_name in tenants:
            print(f"\n🔧 Migrating schema '{schema_name}' (subdomain: {subdomain})")

            # Switch schema
            session.execute(text(f'SET search_path TO "{schema_name}", public'))

            # Add columns to availability_templates
            for statement in ADD_TEMPLATE_COLUMNS_SQL:
                session.execute(text(statement))

            # Create new tables
            session.execute(text(CREATE_TEMPLATE_PROVIDERS_SQL))
            session.execute(text(CREATE_PROVIDER_SCHEDULES_SQL))
            session.execute(text(CREATE_RESOURCE_CAPACITIES_SQL))
            session.execute(text(CREATE_PROVIDER_LEAVES_SQL))

            # Ensure trigger for updated_at exists
            session.execute(text(CREATE_PROVIDER_SCHEDULES_TRIGGER_SQL))

            # Create indexes
            for statement in CREATE_INDEXES_SQL:
                session.execute(text(statement))

            # Apply defaults to existing rows
            session.execute(text("""
                UPDATE availability_templates
                SET template_type = COALESCE(template_type, 'dedicated'),
                    max_concurrent_slots = COALESCE(max_concurrent_slots, 1),
                    requires_provider_assignment = COALESCE(requires_provider_assignment, TRUE)
            """))

            session.commit()
            print(f"✅ Schema '{schema_name}' migrated")

        session.execute(text('SET search_path TO public'))
        session.commit()
        print("\n🎉 Migration completed for all tenants")
        return True

    except Exception as exc:
        session.rollback()
        print(f"❌ Migration failed: {exc}")
        return False

    finally:
        session.close()


if __name__ == "__main__":
    print("🚀 Starting provider availability migration...")
    success = run_migration()
    if not success:
        sys.exit(1)
