# fastapi_app/app/event_types.py - (FINAL CORRECTED VERSION)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from pydantic import BaseModel
from typing import List, Optional
import sys
import re
import datetime

# Import database and models
from .database import SessionLocal
sys.path.append('flask_app/app')
import models

# Import the new default template creator from availability.py
from .availability import get_or_create_default_template

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["event-types"])

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tenant_session(subdomain: str, db: Session = Depends(get_db)):
    """
    A dependency that provides a DB session with the correct search_path.
    """
    schema_name = f"tenant_{subdomain}"
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        yield db
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Tenant '{subdomain}' not found or database error.")


# --- Pydantic Models ---

class EventTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    max_advance_days: int
    is_active: bool
    template_id: Optional[int] = None

class EventTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    max_advance_days: Optional[int] = None
    is_active: Optional[bool] = None
    template_id: Optional[int] = None

class EventTypeResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    duration_minutes: int
    color: str
    is_active: bool
    template_id: Optional[int]
    availability_name: Optional[str] = None
    buffer_before_minutes: int
    buffer_after_minutes: int
    max_bookings_per_day: Optional[int]
    min_notice_hours: int
    max_advance_days: int
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

def create_slug(name: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

# --- API Endpoints ---

@router.get("/event-types", response_model=dict)
async def get_event_types(subdomain: str, db: Session = Depends(get_tenant_session)):
    """Get all event types for a tenant"""
    try:
        event_types = db.query(models.EventType).options(
            joinedload(models.EventType.availability_template)
        ).order_by(models.EventType.created_at.desc()).all()
        
        result = []
        for et in event_types:
            et_dict = EventTypeResponse.from_orm(et).dict()
            et_dict['availability_name'] = et.availability_template.name if et.availability_template else "ไม่ได้กำหนด"
            result.append(et_dict)
        
        return {"event_types": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching event types: {str(e)}")

@router.post("/event-types", response_model=EventTypeResponse)
async def create_event_type(subdomain: str, event_type_data: EventTypeCreate, db: Session = Depends(get_tenant_session)):
    """Create a new event type"""
    try:
        slug = create_slug(event_type_data.name)
        if db.query(models.EventType).filter(models.EventType.slug == slug).first():
            slug = f"{slug}-{int(datetime.datetime.now().timestamp())}"

        template_id = event_type_data.template_id
        if not template_id or not db.query(models.AvailabilityTemplate).filter_by(id=template_id).first():
            template_id = get_or_create_default_template(db)

        event_type_dict = event_type_data.dict()
        event_type_dict['template_id'] = template_id
        
        new_event_type = models.EventType(**event_type_dict)
        new_event_type.slug = slug
        
        # 1. เพิ่ม object ใหม่เข้าไปใน Session
        db.add(new_event_type)
        
        # 2. "ซิงค์" ข้อมูลไปยัง Database เพื่อให้ object ได้รับ ID
        db.flush()
        
        # 3. สร้าง Response object จากข้อมูลที่สมบูรณ์แล้ว
        response_data = EventTypeResponse.from_orm(new_event_type)
        
        # 4. "ยืนยัน" Transaction เพื่อบันทึกข้อมูลอย่างถาวร
        db.commit()
        
        # 5. ส่ง Response กลับไป
        return response_data
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating event type: {str(e)}")

@router.put("/event-types/{event_type_id}", response_model=EventTypeResponse)
async def update_event_type(subdomain: str, event_type_id: int, event_type_data: EventTypeUpdate, db: Session = Depends(get_tenant_session)):
    """Update an event type"""
    try:
        event_type = db.query(models.EventType).filter(models.EventType.id == event_type_id).first()
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        update_data = event_type_data.dict(exclude_unset=True)
        
        if "name" in update_data and update_data["name"] != event_type.name:
            new_slug = create_slug(update_data["name"])
            existing_event_with_slug = db.query(models.EventType).filter(
                models.EventType.slug == new_slug,
                models.EventType.id != event_type_id
            ).first()
            if existing_event_with_slug:
                new_slug = f"{new_slug}-{int(datetime.datetime.now().timestamp())}"
            event_type.slug = new_slug

        for field, value in update_data.items():
            setattr(event_type, field, value)
        
        # *** START OF THE DEFINITIVE FIX ***
        
        # 1. "ซิงค์" ข้อมูลที่แก้ไขไปยัง Database แต่ยังไม่ยืนยัน Transaction
        #    ณ จุดนี้ คำสั่ง UPDATE ได้ถูกส่งไปแล้ว
        db.flush()
        
        # 2. Refresh object ได้อย่างปลอดภัย เพราะ Transaction ยังเปิดอยู่
        db.refresh(event_type)
        
        # 3. สร้าง Response object จากข้อมูลที่อัปเดตล่าสุด
        response_data = EventTypeResponse.from_orm(event_type)
        
        # 4. "ยืนยัน" Transaction ทั้งหมดให้สมบูรณ์
        db.commit()
        
        # 5. ส่ง Response กลับไป
        return response_data
        
        # *** END OF THE DEFINITIVE FIX ***
        
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error updating event type: {str(e)}")

@router.delete("/event-types/{event_type_id}")
async def delete_event_type(subdomain: str, event_type_id: int, db: Session = Depends(get_tenant_session)):
    """Delete an event type"""
    try:
        event_type = db.query(models.EventType).filter(models.EventType.id == event_type_id).first()
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        if db.query(models.Appointment).filter(models.Appointment.event_type_id == event_type_id).first():
            event_type.is_active = False
            db.commit()
            return {"message": "Event type deactivated because it has existing appointments."}
        else:
            db.delete(event_type)
            db.commit()
            return {"message": "Event type deleted successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting event type: {str(e)}")
