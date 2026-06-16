# fastapi_app/app/queue.py — Queue read API (Phase 1.6)
"""
Read endpoints ของระบบคิว (อ่านอย่างเดียว) — ใช้โดย mini-app / จอแสดงคิว ฯลฯ
business logic การเขียนคิว (check-in/transition) อยู่ฝั่ง Flask (Flask-first) — ที่นี่ให้แต่ read

กฎ 0.2 (สำคัญ): ทุก endpoint SET search_path ที่ต้นฟังก์ชัน "โดยไม่ commit ทันที"
(read-only ไม่ต้อง commit เลย) + get_db reset เป็น public ตอน teardown กัน cross-tenant leak
ใช้ Depends(get_db) — ห้ามใช้ Depends(get_tenant_db)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from shared_db.database import SessionLocal, bind_tenant
from shared_db import models
from .tenant import resolve_schema

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["queue"])

BANGKOK = ZoneInfo("Asia/Bangkok")
_ACTIVE = ('checked_in', 'called', 'in_service')


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        # คืน connection สะอาด (rollback + unbind + reset public ให้ติด connection)
        db.rollback()
        bind_tenant(db, None)
        db.execute(text("SET search_path TO public"))
        db.commit()
        db.close()


def _set_tenant(db: Session, subdomain: str) -> None:
    """resolve schema (shared resolver) + ผูก session + SET transaction ปัจจุบัน"""
    schema_name = resolve_schema(db, subdomain)    # query public.hospitals + validate status
    bind_tenant(db, schema_name)                   # transaction ถัดไป ๆ จะถูก SET ให้เองโดย after_begin
    db.execute(text(f'SET search_path TO "{schema_name}", public'))  # transaction ปัจจุบัน


def _today() -> "datetime.date":
    return datetime.now(BANGKOK).date()


# --- response models ---
# จอแสดงคิว/display เป็น public surface (ไม่ auth) — ห้ามเผย patient_ref แม้จะเป็น canonical key
# (patient:{id}/phone:{normalized_phone}); ส่งเฉพาะข้อมูลที่โชว์บนจอได้
class DisplayQueueEntryOut(BaseModel):
    id: int
    queue_number: int | None
    entry_class: str
    status: str

    class Config:
        from_attributes = True


class QueueStatusOut(BaseModel):
    service_point_id: int
    session_date: str
    waiting: int
    serving: int
    in_service: int
    done: int


class QueueDisplayOut(BaseModel):
    service_point_id: int
    service_point_name: str
    session_date: str
    now_serving: list[DisplayQueueEntryOut]
    waiting: list[DisplayQueueEntryOut]


class TicketOut(BaseModel):
    id: int
    queue_number: int | None
    status: str
    session_date: str
    ahead: int


@router.get("/queue/status/{service_point_id}", response_model=QueueStatusOut)
async def queue_status(subdomain: str, service_point_id: int, db: Session = Depends(get_db)):
    _set_tenant(db, subdomain)
    day = _today()
    base = db.query(models.QueueEntry).filter_by(service_point_id=service_point_id, session_date=day)
    return QueueStatusOut(
        service_point_id=service_point_id,
        session_date=day.isoformat(),
        waiting=base.filter(models.QueueEntry.status == 'checked_in').count(),
        serving=base.filter(models.QueueEntry.status.in_(('called', 'in_service'))).count(),
        in_service=base.filter(models.QueueEntry.status == 'in_service').count(),
        done=base.filter(models.QueueEntry.status == 'done').count(),
    )


@router.get("/queue/display/{service_point_id}", response_model=QueueDisplayOut)
async def queue_display(subdomain: str, service_point_id: int, db: Session = Depends(get_db)):
    _set_tenant(db, subdomain)
    sp = db.query(models.ServicePoint).filter_by(id=service_point_id).first()
    if sp is None:
        raise HTTPException(404, "Service point not found")
    day = _today()
    base = db.query(models.QueueEntry).filter_by(service_point_id=service_point_id, session_date=day)
    now_serving = (base.filter(models.QueueEntry.status.in_(('called', 'in_service')))
                   .order_by(models.QueueEntry.queue_number.asc()).all())
    waiting = (base.filter(models.QueueEntry.status == 'checked_in')
               .order_by(models.QueueEntry.queue_number.asc()).limit(20).all())
    return QueueDisplayOut(
        service_point_id=sp.id,
        service_point_name=sp.name,
        session_date=day.isoformat(),
        now_serving=now_serving,
        waiting=waiting,
    )


@router.get("/queue/ticket/{entry_id}", response_model=TicketOut)
async def queue_ticket(subdomain: str, entry_id: int, db: Session = Depends(get_db)):
    _set_tenant(db, subdomain)
    entry = db.query(models.QueueEntry).filter_by(id=entry_id).first()
    if entry is None:
        raise HTTPException(404, "Queue entry not found")
    ahead = (db.query(models.QueueEntry)
             .filter(models.QueueEntry.service_point_id == entry.service_point_id,
                     models.QueueEntry.session_date == entry.session_date,
                     models.QueueEntry.status.in_(_ACTIVE),
                     models.QueueEntry.queue_number < entry.queue_number)
             .count())
    return TicketOut(
        id=entry.id,
        queue_number=entry.queue_number,
        status=entry.status,
        session_date=entry.session_date.isoformat(),
        ahead=ahead,
    )
