"""
Migration: A1 event_types.requires_queue

เพิ่ม flag กลางที่ตัดสินว่า event type นี้ต้องเข้าระบบคิวหรือไม่
(default FALSE เพื่อรักษาพฤติกรรมนัดหมายเดิมแบบ 1:1)

วิธีรัน (ปลอดภัย — default รันแค่ tenant_humnoi):
    python migrations/add_event_types_requires_queue.py
    python migrations/add_event_types_requires_queue.py tenant_ccui
    python migrations/add_event_types_requires_queue.py --all

idempotent: รันซ้ำได้ และไม่แตะ public schema
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL ไม่ถูกตั้งใน .env")
    sys.exit(1)


DDL_STATEMENTS = [
    """
    ALTER TABLE event_types
        ADD COLUMN IF NOT EXISTS requires_queue BOOLEAN DEFAULT FALSE
    """,
    "UPDATE event_types SET requires_queue = FALSE WHERE requires_queue IS NULL",
    "ALTER TABLE event_types ALTER COLUMN requires_queue SET DEFAULT FALSE",
    "ALTER TABLE event_types ALTER COLUMN requires_queue SET NOT NULL",
]


def migrate_schema(conn, schema_name: str) -> None:
    print(f"\n-> migrating schema '{schema_name}' ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))

    for stmt in DDL_STATEMENTS:
        conn.execute(text(stmt))

    conn.execute(text("SET search_path TO public"))
    print(f"  done: event_types.requires_queue")


def resolve_schemas(engine, argv) -> list:
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM public.hospitals ORDER BY id")
            ).fetchall()
        return [r[0] for r in rows]

    explicit = [a for a in argv if not a.startswith("--")]
    if explicit:
        return explicit

    return ["tenant_humnoi"]


def main() -> bool:
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])

    if not schemas:
        print("ไม่พบ tenant schema ที่จะ migrate")
        return True

    print(f"จะ migrate {len(schemas)} schema: {', '.join(schemas)}")
    with engine.begin() as conn:
        for schema_name in schemas:
            migrate_schema(conn, schema_name)
        conn.execute(text("SET search_path TO public"))

    print("\nMigration completed")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
