"""
Migration: Phase 1B.0 — service_points.availability_template_id

เพิ่ม column `availability_template_id` ให้ตาราง service_points เพื่อผูกจุดบริการ
เข้ากับ availability template (ตัว template จริง ไม่ใช่ slot รายวัน) — ใช้เป็น source
ของ session generator (Phase 1B.1+, แผน §5.8)

ความสัมพันธ์: many service_points : one availability_template (nullable —
service_point ที่เป็น walk-in-only ไม่ต้องผูก template ได้)

วิธีรัน (ปลอดภัย — default รันแค่ tenant_humnoi):
    python migrations/add_service_point_availability_template.py                 # tenant_humnoi เท่านั้น
    python migrations/add_service_point_availability_template.py tenant_ccui     # ระบุ schema เอง (รับได้หลายตัว)
    python migrations/add_service_point_availability_template.py --all           # ทุก tenant จาก public.hospitals

idempotent (ADD COLUMN IF NOT EXISTS) — รันซ้ำได้ ไม่แตะ public schema
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


# FK ไป availability_templates(id) — ตัว template จริง (ดู memory queue-1b0-service-point-mapping)
# ON DELETE SET NULL (P1): ลบ template ที่ถูก map → sp unmapped แทน FK-violation (ตรงกับ event_types)
# หมายเหตุ: tenant ที่รัน migration นี้ไปก่อนหน้า (FK เป็น NO ACTION) แก้ด้วย
# migrations/fix_service_point_template_fk_on_delete.py
DDL_STATEMENTS = [
    """
    ALTER TABLE service_points
        ADD COLUMN IF NOT EXISTS availability_template_id
            INTEGER REFERENCES availability_templates(id) ON DELETE SET NULL
    """,
    # index สำหรับ generator ที่ query service_points by template
    """
    CREATE INDEX IF NOT EXISTS idx_service_points_availability_template
        ON service_points (availability_template_id)
    """,
]


def migrate_schema(conn, schema_name: str) -> None:
    """รัน DDL ทั้งหมดใน schema เดียว"""
    print(f"\n→ migrating schema '{schema_name}' ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))

    for stmt in DDL_STATEMENTS:
        conn.execute(text(stmt))

    conn.execute(text("SET search_path TO public"))
    print(f"  ✅ '{schema_name}' done (service_points.availability_template_id + index)")


def resolve_schemas(engine, argv) -> list:
    """ตัดสินใจว่าจะรัน schema ไหนบ้างจาก argv"""
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM public.hospitals ORDER BY id")
            ).fetchall()
        return [r[0] for r in rows]

    explicit = [a for a in argv if not a.startswith("--")]
    if explicit:
        return explicit

    # default ปลอดภัย: humnoi เท่านั้น (ตามที่ตกลงไว้ — รัน+verify ก่อน roll ออก)
    return ["tenant_humnoi"]


def main() -> bool:
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])

    if not schemas:
        print("ไม่พบ tenant schema ที่จะ migrate")
        return True

    print(f"จะ migrate {len(schemas)} schema: {', '.join(schemas)}")
    with engine.begin() as conn:  # transaction เดียวครอบทุก schema — fail แล้ว rollback หมด
        for schema_name in schemas:
            migrate_schema(conn, schema_name)
        conn.execute(text("SET search_path TO public"))

    print("\n🎉 Migration completed")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
