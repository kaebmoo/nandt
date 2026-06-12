# fastapi_app/app/holidays.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, exc, extract
from pydantic import BaseModel, Field
from typing import List, Optional, Set
from datetime import date
import logging
from threading import Lock

from shared_db.database import SessionLocal
from shared_db import models
from .holiday_service import HolidayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["holidays"])

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models ---
class HolidayBase(BaseModel):
    date: date
    name: str
    source: str = 'manual'
    description: Optional[str] = None

class HolidayCreate(HolidayBase):
    pass

class HolidayUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    description: Optional[str] = None

class HolidayResponse(HolidayBase):
    id: int
    is_active: bool
    is_recurring: bool
    
    class Config:
        from_attributes = True

class SyncRequest(BaseModel):
    year: int = Field(default_factory=lambda: date.today().year)
    holidays: List[HolidayBase]


_initialized_tenants: Set[str] = set()
_tenant_lock = Lock()


def ensure_holiday_table(subdomain: str, db: Session):
    schema_key = subdomain or ""
    with _tenant_lock:
        if schema_key in _initialized_tenants:
            return

        try:
            exists = db.execute(text("SELECT to_regclass('holidays')")).scalar()
            if not exists:
                logger.info("Creating holidays table for tenant '%s'", subdomain)
                # db.connection() ไม่ใช่ get_bind() — ให้ CREATE TABLE ใช้ connection
                # เดียวกับที่ SET search_path ไว้ ไม่งั้นตารางไปโผล่ public schema
                models.Holiday.__table__.create(bind=db.connection(), checkfirst=True)
                db.commit()
        except Exception:
            db.rollback()
            raise
        else:
            _initialized_tenants.add(schema_key)


def sync_tenant_holidays(db: Session, schema_name: str, year: int = None, holidays: list = None) -> dict:
    """เติมวันหยุดราชการเข้า tenant schema (idempotent — ข้ามวันที่ที่มีอยู่แล้ว)

    holidays=None จะดึงจาก BOT API ของปีที่ระบุ (ต้องตั้ง BOT_TOKEN ใน .env)
    เป็น logic กลางที่ใช้ร่วมกันโดย: endpoint /holidays/sync (รวมถึง Celery job ประจำปี)
    และการสร้าง tenant ใหม่ทั้งจาก /api/register และ Super Admin panel
    จัดการ search_path เองและ reset กลับ public เสมอ
    """
    if year is None:
        year = date.today().year
    if holidays is None:
        holidays = HolidayService.fetch_from_bot_api(year)

    subdomain = schema_name.replace('tenant_', '', 1)
    added = 0
    skipped = 0
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        ensure_holiday_table(subdomain, db)

        for item in holidays or []:
            get = item.get if isinstance(item, dict) else lambda k, d=None: getattr(item, k, d)
            holiday_date = get('date')
            if not holiday_date:
                continue
            if db.query(models.Holiday).filter_by(date=holiday_date).first():
                skipped += 1
                continue
            db.add(models.Holiday(
                date=holiday_date,
                name=get('name') or 'วันหยุด',
                source=get('source') or 'manual',
                description=get('description'),
                is_active=True,
                is_recurring=False,
            ))
            added += 1

        db.commit()
        return {'added': added, 'skipped': skipped}
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(text('SET search_path TO public'))
        db.commit()

# --- API Endpoints ---
@router.get("/holidays", response_model=List[HolidayResponse])
async def get_holidays(
    subdomain: str,
    year: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get holidays with optional filters."""
    schema_name = f"tenant_{subdomain}"

    # Set search_path (ไม่ commit — ให้ SET อยู่ใน transaction เดียวกับ query
    # มิฉะนั้น connection อาจถูกสลับใน pool แล้ว query หลุดไป public schema)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))

    try:
        ensure_holiday_table(subdomain, db)
        
        query = db.query(models.Holiday)
        
        if year:
            query = query.filter(extract('year', models.Holiday.date) == year)
        
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        else:
            query = query.filter_by(is_active=True)
        
        holidays = query.order_by(models.Holiday.date).all()
        return holidays if holidays else []
        
    except Exception as e:
        logger.error(f"Error fetching holidays: {str(e)}")
        return []

@router.post("/holidays/sync", response_model=dict)
async def sync_holidays(
    subdomain: str,
    payload: SyncRequest,
    db: Session = Depends(get_db)
):
    """Syncs holidays from an external source."""
    schema_name = f"tenant_{subdomain}"

    logger.info(f"Syncing holidays for {subdomain}, year: {payload.year}")
    logger.info(f"Received {len(payload.holidays)} holidays")

    holidays = [h.dict() for h in payload.holidays] if payload.holidays else None

    try:
        result = sync_tenant_holidays(db, schema_name, year=payload.year, holidays=holidays)
        logger.info(f"Committed: Added {result['added']}, Skipped {result['skipped']}")
        return {"message": f"Sync completed. Added: {result['added']}, Skipped: {result['skipped']}."}
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/holidays", response_model=HolidayResponse)
async def create_custom_holiday(
    subdomain: str,
    holiday: HolidayCreate,
    db: Session = Depends(get_db)
):
    """Creates a single custom holiday."""
    schema_name = f"tenant_{subdomain}"

    # Set search_path (ไม่ commit — ดูเหตุผลที่ get_holidays)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))

    try:
        ensure_holiday_table(subdomain, db)

        exists = db.query(models.Holiday).filter_by(date=holiday.date).first()
        if exists:
            raise HTTPException(status_code=409, detail=f"Holiday on {holiday.date} already exists.")

        db_holiday = models.Holiday(
            date=holiday.date,
            name=holiday.name,
            source=holiday.source,
            description=getattr(holiday, 'description', None),
            is_active=True,
            is_recurring=False
        )
        db.add(db_holiday)
        db.commit()
        # commit จบ transaction แล้ว — ต้อง SET ใหม่ก่อน refresh ไม่งั้นอาจอ่านผิด schema
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        db.refresh(db_holiday)

        return db_holiday
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating holiday: {str(e)}")

@router.get("/holidays/{holiday_id}", response_model=HolidayResponse)
async def get_holiday(
    subdomain: str,
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Get a single holiday by ID."""
    schema_name = f"tenant_{subdomain}"

    # Set search_path (ไม่ commit — ดูเหตุผลที่ get_holidays)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))

    ensure_holiday_table(subdomain, db)

    holiday = db.query(models.Holiday).filter_by(id=holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found.")
    return holiday

@router.patch("/holidays/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    subdomain: str,
    holiday_id: int,
    update_data: HolidayUpdate,
    db: Session = Depends(get_db)
):
    """Update holiday (partial update)."""
    schema_name = f"tenant_{subdomain}"

    # Set search_path (ไม่ commit — ดูเหตุผลที่ get_holidays)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))

    try:
        ensure_holiday_table(subdomain, db)

        holiday = db.query(models.Holiday).filter_by(id=holiday_id).first()
        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found.")

        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(holiday, field):
                setattr(holiday, field, value)

        db.commit()
        # commit จบ transaction แล้ว — ต้อง SET ใหม่ก่อน refresh ไม่งั้นอาจอ่านผิด schema
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        db.refresh(holiday)
        return holiday
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating: {str(e)}")

@router.delete("/holidays/{holiday_id}", status_code=204)
async def delete_holiday(
    subdomain: str,
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Deletes a holiday."""
    schema_name = f"tenant_{subdomain}"

    # Set search_path (ไม่ commit — ดูเหตุผลที่ get_holidays)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))

    try:
        ensure_holiday_table(subdomain, db)

        holiday = db.query(models.Holiday).filter_by(id=holiday_id).first()
        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found.")
        
        db.delete(holiday)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting: {str(e)}")
    
@router.get("/holidays/fetch/{year}")
async def fetch_holidays_for_year(
    subdomain: str,
    year: int,
    db: Session = Depends(get_db)
):
    """Fetch holidays from external API"""
    holidays = HolidayService.fetch_from_bot_api(year)
    return {"holidays": holidays}