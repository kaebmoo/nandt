"""
Migration: partial unique index กัน "appointment เดียวมี active queue entry หลายแถว"

เป็น DB backstop ของ idempotency ใน queue_service.check_in (กัน race สแกน QR appointment เดิมพร้อมกัน)
active = status IN ('checked_in','called','in_service'); appointment ที่ done/no_show/skipped แล้ว
check-in ใหม่ได้ (มาหลายรอบในวันได้)

วิธีรัน (default tenant_humnoi; --all = ทุก tenant):
    python migrations/add_queue_active_appointment_unique_index.py
    python migrations/add_queue_active_appointment_unique_index.py --all
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL ไม่ถูกตั้งใน .env")
    sys.exit(1)

INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_queue_active_appointment
ON queue_entries (appointment_id)
WHERE appointment_id IS NOT NULL AND status IN ('checked_in','called','in_service')
"""


def resolve_schemas(engine, argv):
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT schema_name FROM public.hospitals ORDER BY id")).fetchall()
        return [r[0] for r in rows]
    explicit = [a for a in argv if not a.startswith("--")]
    return explicit or ["tenant_humnoi"]


def main():
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])
    print(f"จะเพิ่ม index ใน {len(schemas)} schema: {', '.join(schemas)}")
    with engine.begin() as conn:
        for schema_name in schemas:
            conn.execute(text(f'SET search_path TO "{schema_name}", public'))
            conn.execute(text(INDEX_SQL))
            print(f"  ✅ {schema_name}: uq_queue_active_appointment")
        conn.execute(text("SET search_path TO public"))
    print("🎉 done")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
