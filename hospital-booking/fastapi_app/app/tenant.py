# fastapi_app/app/tenant.py
"""
Shared tenant resolver สำหรับ FastAPI — ที่เดียวที่ resolve subdomain -> schema_name

ใช้แทนการ hardcode `f"tenant_{subdomain}"` ทุกที่ เพราะ registration sanitize schema name
(strip อักขระที่ไม่ใช่ alnum, main.py: create_tenant_setup) เช่น subdomain `my-clinic`
-> schema `tenant_myclinic` ไม่ใช่ `tenant_my-clinic`. การ reconstruct เองจะหา schema ผิด -> UndefinedTable

resolve จาก public.hospitals.schema_name จริง + validate status (เหมือน Flask middleware / queue.py)
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from shared_db import models


def resolve_schema(db: Session, subdomain: str) -> str:
    """คืน schema_name จริงของ tenant จาก public.hospitals (raise 404/503 ถ้าไม่เจอ/ถูกปิด)

    ไม่ bind/SET — แค่ resolve + validate. ให้ caller (helper ที่ bind+SET) ใช้ schema_name นี้ต่อ
    Hospital model มี __table_args__ schema='public' จึง query ได้แม้ session ยังไม่ผูก tenant
    """
    hospital = db.query(models.Hospital).filter_by(subdomain=subdomain).first()
    if hospital is None or hospital.status == models.HospitalStatus.DELETED:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {subdomain}")
    if hospital.status == models.HospitalStatus.INACTIVE:
        raise HTTPException(status_code=503, detail=f"Tenant is not active: {subdomain}")
    return hospital.schema_name
