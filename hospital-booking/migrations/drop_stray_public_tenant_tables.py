# migrations/drop_stray_public_tenant_tables.py
"""
ลบตารางของ tenant (TenantBase) ที่หลงไปอยู่ใน public schema จาก migration เก่า

ทำไมต้องลบ: ตารางพวกนี้ (ว่างเปล่า) ทำให้ query ที่ search_path หลุดไป public
"หาไม่เจอแบบเงียบๆ" แทนที่จะ error ชัดเจน — เป็นต้นเหตุของบั๊กที่ debug ยากมาก
(ดู CLAUDE.md หัวข้อ "กับดัก search_path")

ความปลอดภัย:
  - แตะเฉพาะ public schema เท่านั้น ไม่แตะ tenant_* schemas
  - ไม่แตะ public.hospitals / public.users (ตารางจริงของ PublicBase)
  - ตารางที่ "มีข้อมูล" จะไม่ลบ เว้นแต่ใส่ --force (และจะ backup เป็น JSON ก่อนเสมอ)

วิธีใช้:
  python drop_stray_public_tenant_tables.py            # dry-run: แสดงว่าจะทำอะไร ไม่ลบจริง
  python drop_stray_public_tenant_tables.py --execute  # ลบตารางว่าง + backup ตารางที่มีข้อมูลไว้ก่อน (ไม่ลบ)
  python drop_stray_public_tenant_tables.py --execute --force  # ลบทุกตารางรวมที่มีข้อมูล (backup ก่อน)
"""

import os
import sys
import json
import argparse
from datetime import datetime, date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from shared_db.database import engine
from shared_db import models

PROTECTED = {'hospitals', 'users'}  # ตารางจริงของ public schema ห้ามแตะเด็ดขาด


def tenant_table_names():
    names = {t.split('.')[-1] for t in models.TenantBase.metadata.tables.keys()}
    return sorted(names - PROTECTED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='ลบจริง (default คือ dry-run)')
    parser.add_argument('--force', action='store_true', help='ลบตารางที่มีข้อมูลด้วย (backup ก่อนเสมอ)')
    args = parser.parse_args()

    candidates = tenant_table_names()
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')

    with engine.connect() as conn:
        existing = {
            r[0] for r in conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            ))
        }
        strays = [t for t in candidates if t in existing]

        if not strays:
            print("ไม่พบตาราง tenant หลงอยู่ใน public schema — ไม่มีอะไรต้องทำ")
            return

        print(f"พบตาราง tenant ใน public schema {len(strays)} ตาราง:")
        plan = []  # (table, row_count, action)
        for t in strays:
            n = conn.execute(text(f'SELECT COUNT(*) FROM public."{t}"')).scalar()
            if n == 0:
                action = 'DROP'
            elif args.force:
                action = 'BACKUP+DROP'
            else:
                action = 'BACKUP (ไม่ลบ — มีข้อมูล ใช้ --force ถ้าต้องการลบ)'
            plan.append((t, n, action))
            print(f"  public.{t:<28} {n:>5} แถว → {action}")

        if not args.execute:
            print("\n(dry-run) ยังไม่ได้ลบอะไร — รันด้วย --execute เพื่อทำจริง")
            return

        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # ใช้ transaction แยกตอนทำจริง
    with engine.begin() as conn:
        for t, n, action in plan:
            if n > 0:
                rows = conn.execute(text(f'SELECT * FROM public."{t}"'))
                data = [
                    {k: (v.isoformat() if isinstance(v, (datetime, date)) else v)
                     for k, v in dict(r._mapping).items()}
                    for r in rows
                ]
                path = os.path.join(backup_dir, f'public_{t}_{stamp}.json')
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=1, default=str)
                print(f"💾 backup public.{t} ({n} แถว) → {path}")

            if action == 'DROP' or (action.startswith('BACKUP+') and args.force):
                conn.execute(text(f'DROP TABLE public."{t}" CASCADE'))
                print(f"🗑️  DROP public.{t}")

    print("\nเสร็จสิ้น — ตรวจระบบต่อด้วยการลองจองผ่านหน้า public booking ของ tenant ใดก็ได้")


if __name__ == '__main__':
    main()
