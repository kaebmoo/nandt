"""
Pytest fixtures for queue/messaging tests.

แต่ละ test ทำงานบน tenant schema ชั่วคราว (สร้างจาก models, drop ทิ้งหลังเทส) เพื่อไม่แตะข้อมูลจริง
ต้องมี DATABASE_URL ใน .env (ใช้ DB เดียวกับ dev — ต่างกันแค่ schema)
"""

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared_db import models
from shared_db.database import bind_tenant   # ใช้ mechanism จริง (session.info + after_begin)

load_dotenv()

TEST_SCHEMA = "test_queue"


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    # ไม่ต้องผูก search_path ที่ engine — ใช้ bind_tenant(session, schema) + event after_begin
    # (event อยู่บน Session class ระดับ global ใน database.py จึงทำงานกับ session ของ engine นี้ด้วย)
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture()
def test_schema(engine):
    """สร้าง schema ทดสอบใหม่ + สร้างตาราง tenant ทั้งหมดจาก models, drop หลังเทส"""
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {TEST_SCHEMA}'))
        conn.execute(text(f'SET search_path TO {TEST_SCHEMA}, public'))
        models.TenantBase.metadata.create_all(bind=conn)
        conn.execute(text('SET search_path TO public'))
    yield TEST_SCHEMA
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE'))


@pytest.fixture()
def make_session(engine, test_schema):
    """factory: คืน Session ใหม่ที่ตั้ง search_path ไป schema ทดสอบแล้ว (ใช้สร้างหลาย session ใน concurrency test)"""
    factory = sessionmaker(bind=engine)
    created = []

    def _make():
        s = factory()
        bind_tenant(s, test_schema)   # ผูกก่อน query แรก -> after_begin SET search_path ให้ทุก txn
        created.append(s)
        return s

    yield _make
    for s in created:
        try:
            s.close()
        except Exception:
            pass


@pytest.fixture()
def db(make_session):
    s = make_session()
    yield s
    s.rollback()


@pytest.fixture()
def service_point(db):
    sp = models.ServicePoint(name="จุดทดสอบ", sp_type="counter", parallel_servers=1)
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp
