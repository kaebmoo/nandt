# fastapi_app/app/holidays.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, exc, extract
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
import logging

from shared_db.database import SessionLocal
from shared_db import models

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
    
    # Set search_path
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
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
    
    # Set search_path
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    logger.info(f"Syncing holidays for {subdomain}, year: {payload.year}")
    logger.info(f"Received {len(payload.holidays)} holidays")
    
    try:
        added_count = 0
        skipped_count = 0
        
        for holiday_data in payload.holidays:
            exists = db.query(models.Holiday).filter_by(date=holiday_data.date).first()
            if not exists:
                new_holiday = models.Holiday(
                    date=holiday_data.date,
                    name=holiday_data.name,
                    source=holiday_data.source,
                    description=getattr(holiday_data, 'description', None),
                    is_active=True,
                    is_recurring=False
                )
                db.add(new_holiday)
                added_count += 1
                logger.debug(f"Added: {holiday_data.date} - {holiday_data.name}")
            else:
                skipped_count += 1
                logger.debug(f"Skipped: {holiday_data.date} (exists)")
        
        db.commit()
        logger.info(f"Committed: Added {added_count}, Skipped {skipped_count}")
        
        return {"message": f"Sync completed. Added: {added_count}, Skipped: {skipped_count}."}
        
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/holidays", response_model=HolidayResponse)
async def create_custom_holiday(
    subdomain: str,
    holiday: HolidayCreate,
    db: Session = Depends(get_db)
):
    """Creates a single custom holiday."""
    schema_name = f"tenant_{subdomain}"
    
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
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
    
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
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
    
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
        holiday = db.query(models.Holiday).filter_by(id=holiday_id).first()
        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found.")
        
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(holiday, field):
                setattr(holiday, field, value)
        
        db.commit()
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
    
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
        holiday = db.query(models.Holiday).filter_by(id=holiday_id).first()
        if not holiday:
            raise HTTPException(status_code=404, detail="Holiday not found.")
        
        db.delete(holiday)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting: {str(e)}")