# hospital-booking/shared_db/database.py
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from flask import g
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- Per-session tenant search_path (root fix สำหรับบั๊ก connection-pool/search_path) ---
# ปัญหาเดิม: SET search_path เป็น connection-scoped (อยู่รอด COMMIT แต่ถูก ROLLBACK ย้อนกลับ)
# พอ pool หยิบ connection ใหม่หลัง commit/rollback -> search_path หลุด -> UndefinedTable / leak
# วิธีแก้ที่ราก: ผูก schema กับ "session" (session.info['tenant_schema']) แล้ว event after_begin
# SET search_path ให้ทุก transaction ที่ session เปิด (รวม transaction ใหม่หลัง commit/rollback)
# -> service ไม่ต้อง re-SET เองอีก
#   - bound session   -> SET tenant ทุก transaction
#   - unbound session -> SET public ทุก transaction (ไม่ใช่ no-op!) กัน connection ที่ค้าง tenant path
#     จาก pool ปนเปื้อน session ที่ไม่ได้ผูก tenant. **ผลข้างเคียง:** code ที่ SET search_path เองแบบ
#     manual (ไม่ bind) แล้ว commit()/rollback() แล้ว query ต่อ จะพัง — ต้องใช้ bind_tenant() เสมอ
#     (legacy FastAPI tenant endpoints ทุกตัว migrate มาใช้ bind_tenant แล้ว มิ.ย. 2026)
@event.listens_for(Session, "after_begin")
def _apply_tenant_search_path(session, transaction, connection):
    # exec_driver_sql = รันตรงบน DBAPI cursor ไม่ trigger event ซ้ำ (กัน recursion)
    schema = session.info.get("tenant_schema")
    if schema:
        connection.exec_driver_sql(f'SET search_path TO "{schema}", public')
    else:
        # session ที่ "ไม่ได้ผูก tenant" -> บังคับ public เสมอทุก transaction
        # สำคัญ: connection ใน pool อาจค้าง tenant search_path จาก request ก่อน (SET อยู่รอด COMMIT)
        # ถ้าไม่ set public ที่นี่ unbound session จะหยิบ connection ที่ปนเปื้อน tenant ไปใช้
        # (cross-tenant contamination). การ reset ที่ teardown อย่างเดียวไม่พอ เพราะ get_db บาง
        # ตัว (เช่น booking.py) ไม่ได้ reset connection ก่อนคืน pool
        connection.exec_driver_sql("SET search_path TO public")


def bind_tenant(session, schema_name):
    """ผูก session เข้ากับ tenant schema (เรียกก่อนใช้ session กับข้อมูล tenant)

    หลังเรียก ทุก transaction ของ session (รวมหลัง commit/refresh/rollback) จะ SET search_path
    ให้อัตโนมัติผ่าน after_begin — caller ไม่ต้อง re-SET เอง
    schema_name = 'tenant_<subdomain>' ; ส่ง None/'' เพื่อปลดการผูก
    """
    if schema_name:
        session.info["tenant_schema"] = schema_name
    else:
        session.info.pop("tenant_schema", None)


# --- Declarative Bases ---
# สร้าง Base แยกสำหรับ public และ tenant schemas ตามโครงสร้างใน models.py
PublicBase = declarative_base()
TenantBase = declarative_base()

# --- Session Helper ---
def get_db_session():
    """
    ดึง database session สำหรับ request ปัจจุบันจาก `g` object ของ Flask
    หากยังไม่มี session จะทำการสร้างใหม่และผูกไว้กับ `g`
    """
    if 'db' not in g or g.db is None:
        g.db = SessionLocal()
    return g.db