"""
Migration: queue_entries.arrived_ack_at (Patch 21 มิ.ย. 2026 — §4.4).

Adds the "ถึงหน้าห้องแล้ว" acknowledgement timestamp set by patient (status page)
or staff (console). Not a status, not a gate — the called-timeout sweeper just
excludes entries that have it set. Idempotent ADD COLUMN IF NOT EXISTS.

    python migrations/add_queue_arrived_ack.py            # tenant_humnoi (default safe)
    python migrations/add_queue_arrived_ack.py tenant_x   # explicit schema
    python migrations/add_queue_arrived_ack.py --all      # all tenants from public.hospitals
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL is not set")
    sys.exit(1)


DDL_STATEMENTS = [
    "ALTER TABLE queue_entries ADD COLUMN IF NOT EXISTS arrived_ack_at TIMESTAMPTZ",
]


def resolve_schemas(engine, argv) -> list[str]:
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM public.hospitals ORDER BY id")
            ).fetchall()
        return [row[0] for row in rows]

    explicit = [arg for arg in argv if not arg.startswith("--")]
    return explicit or ["tenant_humnoi"]


def migrate_schema(conn, schema_name: str) -> None:
    print(f"migrating {schema_name} ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))
    exists = conn.execute(text("SELECT to_regclass('queue_entries')")).scalar()
    if exists is None:
        print(f"  skipped {schema_name}: queue_entries does not exist")
        return
    for stmt in DDL_STATEMENTS:
        conn.execute(text(stmt))
    print(f"  done {schema_name}")


def main() -> bool:
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])
    with engine.begin() as conn:
        for schema_name in schemas:
            migrate_schema(conn, schema_name)
        conn.execute(text("SET search_path TO public"))
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
