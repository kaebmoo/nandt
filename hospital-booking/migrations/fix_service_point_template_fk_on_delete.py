"""
Migration: P1 fix — service_points.availability_template_id FK → ON DELETE SET NULL

ปัญหา: 1B.0 (add_service_point_availability_template.py) สร้าง FK แบบ NO ACTION → ลบ
availability_template ที่ถูก map กับ service_point จะเจอ FK violation แล้วโดน wrap เป็น 500
(delete_availability_template ไม่ได้ clear mapping ก่อนลบ)

แก้: drop constraint เดิม แล้วสร้างใหม่เป็น ON DELETE SET NULL — ลบ template ที่ถูก map →
service_points.availability_template_id กลายเป็น NULL (sp unmapped) แทนที่จะพัง
(ตรงกับ event_types.template_id ที่เป็น ON DELETE SET NULL อยู่แล้ว)

idempotent by construction: DROP CONSTRAINT IF EXISTS + ADD เสมอ → ผลลัพธ์เป็น SET NULL เสมอ
(ไม่ skip ตาม confdeltype — conname ซ้ำได้ข้าม schema ทำให้เช็คแบบ by-conname ตอบผิด schema)

วิธีรัน (ปลอดภัย — default tenant_humnoi เท่านั้น):
    python migrations/fix_service_point_template_fk_on_delete.py                 # humnoi เท่านั้น
    python migrations/fix_service_point_template_fk_on_delete.py tenant_ccui     # ระบุเอง
    python migrations/fix_service_point_template_fk_on_delete.py --all           # ทุก tenant จาก public.hospitals
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

_CONSTRAINT = "service_points_availability_template_id_fkey"


def migrate_schema(conn, schema_name: str) -> None:
    print(f"\n→ migrating schema '{schema_name}' ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))

    # drop เดิม (ถ้ามี) แล้วสร้างใหม่เป็น ON DELETE SET NULL — idempotent by construction
    # (DROP IF EXISTS + ADD เสมอ → ผลลัพธ์เป็น SET NULL เสมอ ไม่ว่าเดิมเป็นอะไร)
    # NB: ห้ามเช็ค pg_constraint by conname เฉย ๆ เพื่อ skip — conname ซ้ำได้ข้าม schema
    # (.scalar() จะหยิบ row ของ schema อื่นมาตอบผิด) ถ้าจะเช็คต้อง join pg_namespace ตาม schema
    conn.execute(text(f'ALTER TABLE service_points DROP CONSTRAINT IF EXISTS {_CONSTRAINT}'))
    conn.execute(text(
        f'ALTER TABLE service_points ADD CONSTRAINT {_CONSTRAINT} '
        f'FOREIGN KEY (availability_template_id) '
        f'REFERENCES availability_templates(id) ON DELETE SET NULL'
    ))
    conn.execute(text("SET search_path TO public"))
    print(f"  ✅ '{schema_name}' FK → ON DELETE SET NULL")


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
    return ["tenant_humnoi"]   # default ปลอดภัย: humnoi ก่อน + verify ก่อน roll


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
    print("\n🎉 Migration completed")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
