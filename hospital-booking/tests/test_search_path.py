"""
Regression tests สำหรับ search_path mechanism ระดับ session (root fix):
  shared_db.database.bind_tenant(session, schema) + event after_begin

คุณสมบัติที่ต้องรักษา: เมื่อ session ถูกผูก tenant แล้ว ทุก transaction ของ session
(รวม transaction ใหม่หลัง commit/rollback ที่หยิบ connection ใหม่จาก pool) ต้องมี search_path
ชี้ tenant schema เสมอ — service จึงไม่ต้อง re-SET เอง
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from shared_db import models
from shared_db.database import bind_tenant


def test_bound_session_has_tenant_search_path(make_session):
    s = make_session()           # fixture ผูก session กับ test schema ให้แล้ว
    assert "test_queue" in s.execute(text("SHOW search_path")).scalar()
    s.close()


def test_search_path_reapplied_after_commit(make_session):
    """เคสบั๊กเดิม: commit -> connection ใหม่จาก pool -> search_path หลุด. ต้องถูก SET ใหม่ให้เอง"""
    s = make_session()
    s.add(models.ServicePoint(name="x", sp_type="room", parallel_servers=1))
    s.commit()
    # transaction ใหม่หลัง commit
    assert "test_queue" in s.execute(text("SHOW search_path")).scalar()
    assert s.query(models.ServicePoint).count() >= 1     # query tenant table หลัง commit ไม่ UndefinedTable
    s.close()


def test_search_path_reapplied_after_rollback(make_session):
    """finding 4: rollback ย้อน SET search_path กลับ public — after_begin ต้อง SET ใหม่ให้ transaction ถัดไป"""
    s = make_session()
    s.add(models.ServicePoint(name="y", sp_type="room", parallel_servers=1))
    s.flush()
    s.rollback()
    assert "test_queue" in s.execute(text("SHOW search_path")).scalar()
    s.query(models.ServicePoint).count()                 # ไม่ UndefinedTable หลัง rollback
    s.close()


def test_multiple_commits_keep_tenant_search_path(make_session):
    """commit หลายรอบติดกัน (จำลอง service ที่ commit แล้ว query ต่อ) — search_path ต้องอยู่ครบ"""
    s = make_session()
    for i in range(3):
        s.add(models.ServicePoint(name=f"sp{i}", sp_type="room", parallel_servers=1))
        s.commit()
        assert "test_queue" in s.execute(text("SHOW search_path")).scalar()
    assert s.query(models.ServicePoint).count() == 3
    s.close()


def test_unbound_session_not_contaminated_by_returned_tenant_connection():
    """เคสที่ reviewer พิสูจน์ว่า fail: bound session ใช้ tenant แล้วคืน connection เข้า pool
    -> unbound session หยิบ connection เดิมต้องเห็น public ไม่ใช่ tenant ที่ค้าง (cross-tenant)

    บังคับ pool_size=1 + max_overflow=0 ให้ s2 ได้ "connection เดียวกัน" กับ s1 แน่ ๆ (deterministic)
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        import pytest
        pytest.skip("DATABASE_URL not set")
    eng = create_engine(url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    try:
        Session = sessionmaker(bind=eng)

        # 1) bound session ใช้ tenant_humnoi แล้ว commit + close (connection กลับ pool)
        s1 = Session()
        bind_tenant(s1, "tenant_humnoi")
        s1.execute(text("SELECT 1"))                 # force transaction -> after_begin SET tenant
        assert "tenant_humnoi" in s1.execute(text("SHOW search_path")).scalar()
        s1.commit()                                  # SET tenant อยู่รอด commit (ค้างบน connection)
        s1.close()                                   # connection (ตัวเดียวใน pool) กลับ pool

        # 2) unbound session ใหม่ -> ได้ connection เดิม -> after_begin ต้อง SET public ให้
        s2 = Session()                               # ไม่ bind tenant
        path = s2.execute(text("SHOW search_path")).scalar()
        s2.close()
        assert "tenant_humnoi" not in path, f"unbound session ปนเปื้อน tenant path: {path!r}"
        assert "public" in path
    finally:
        eng.dispose()
