# fastapi_app/app/event_types.py - Enhanced with availability validation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
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

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["event-types"])

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tenant_db(subdomain: str, db: Session):
    """Set database search path to tenant schema"""
    schema_name = f"tenant_{subdomain}"
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        return db
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {subdomain}")

def get_or_assign_default_availability(db: Session, availability_id: Optional[int] = None) -> int:
    """หาหรือสร้าง default availability และตรวจสอบ availability_id ที่ส่งมา"""
    
    # ถ้ามี availability_id ให้ตรวจสอบว่ายังใช้ได้หรือไม่
    if availability_id:
        existing_availability = db.query(models.Availability).filter(
            models.Availability.id == availability_id,
            models.Availability.is_active == True
        ).first()
        if existing_availability:
            return availability_id
    
    # หา default availability ที่มีอยู่แล้ว
    default_availability = db.query(models.Availability).filter(
        models.Availability.name == "เวลาทำการเริ่มต้น",
        models.Availability.is_active == True
    ).first()
    
    if default_availability:
        return default_availability.id
    
    # สร้าง default availability ใหม่
    from .availability import get_or_create_default_availability
    return get_or_create_default_availability(db)

# --- Pydantic Models ---
class EventTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int = 30
    price: Optional[float] = None
    currency: str = "THB"
    buffer_time_minutes: int = 0
    advance_booking_days: int = 30
    requires_confirmation: bool = False
    is_active: bool = True
    availability_id: Optional[int] = None

class EventTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    buffer_time_minutes: Optional[int] = None
    advance_booking_days: Optional[int] = None
    requires_confirmation: Optional[bool] = None
    is_active: Optional[bool] = None
    availability_id: Optional[int] = None

class EventTypeResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    duration_minutes: int
    color: str
    is_active: bool
    availability_id: Optional[int]
    availability_name: Optional[str] = None  # เพิ่มชื่อ availability
    buffer_before_minutes: int
    buffer_after_minutes: int
    max_bookings_per_day: Optional[int]
    min_notice_hours: int
    max_advance_days: int
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

def create_slug(name: str) -> str:
    """Create URL slug from name"""
    # Convert to lowercase, replace spaces and special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

# --- API Endpoints ---

@router.get("/event-types", response_model=dict)
async def get_event_types(subdomain: str, db: Session = Depends(get_db)):
    """Get all event types for a tenant with availability info"""
    try:
        get_tenant_db(subdomain, db)
        
        event_types = db.query(models.EventType).order_by(models.EventType.created_at.desc()).all()
        
        # เพิ่มข้อมูล availability name
        result = []
        for et in event_types:
            et_dict = EventTypeResponse.from_orm(et).dict()
            
            # หาชื่อ availability
            if et.availability_id:
                availability = db.query(models.Availability).filter(
                    models.Availability.id == et.availability_id
                ).first()
                et_dict['availability_name'] = availability.name if availability else "ไม่พบข้อมูล"
            else:
                et_dict['availability_name'] = "ไม่ได้กำหนด"
            
            result.append(et_dict)
        
        return {"event_types": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/event-types/{event_type_id}", response_model=EventTypeResponse)
async def get_event_type(subdomain: str, event_type_id: int, db: Session = Depends(get_db)):
    """Get a specific event type"""
    try:
        get_tenant_db(subdomain, db)
        
        event_type = db.query(models.EventType).filter(
            models.EventType.id == event_type_id
        ).first()
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        return EventTypeResponse.from_orm(event_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/event-types", response_model=EventTypeResponse)
async def create_event_type(subdomain: str, event_type_data: EventTypeCreate, db: Session = Depends(get_db)):
    """Create a new event type"""
    try:
        get_tenant_db(subdomain, db)
        
        # Generate slug
        slug = create_slug(event_type_data.name)
        
        # Check if slug already exists
        existing = db.query(models.EventType).filter(models.EventType.slug == slug).first()
        if existing:
            # Make slug unique
            counter = 1
            while existing:
                new_slug = f"{slug}-{counter}"
                existing = db.query(models.EventType).filter(models.EventType.slug == new_slug).first()
                if not existing:
                    slug = new_slug
                    break
                counter += 1
        
        # ใช้ function ใหม่สำหรับจัดการ availability
        availability_id = get_or_assign_default_availability(db, event_type_data.availability_id)

        # Create event type
        event_type = models.EventType(
            name=event_type_data.name,
            slug=slug,
            description=event_type_data.description,
            duration_minutes=event_type_data.duration_minutes,
            availability_id=availability_id,
            buffer_before_minutes=event_type_data.buffer_time_minutes,
            buffer_after_minutes=event_type_data.buffer_time_minutes,
            min_notice_hours=4,  # default
            max_advance_days=event_type_data.advance_booking_days,
            is_active=event_type_data.is_active
        )
        
        db.add(event_type)
        db.commit()
        db.refresh(event_type)
        
        return EventTypeResponse.from_orm(event_type)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/event-types/{event_type_id}", response_model=EventTypeResponse)
async def update_event_type(subdomain: str, event_type_id: int, event_type_data: EventTypeUpdate, db: Session = Depends(get_db)):
    """Update an event type"""
    try:
        get_tenant_db(subdomain, db)
        
        event_type = db.query(models.EventType).filter(
            models.EventType.id == event_type_id
        ).first()
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        # Update fields that are provided
        update_data = event_type_data.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            if field == "buffer_time_minutes":
                # Map to both buffer fields
                event_type.buffer_before_minutes = value
                event_type.buffer_after_minutes = value
            elif field == "advance_booking_days":
                event_type.max_advance_days = value
            elif field == "availability_id":
                # ใช้ function สำหรับตรวจสอบ availability
                event_type.availability_id = get_or_assign_default_availability(db, value)
            elif hasattr(event_type, field):
                setattr(event_type, field, value)
        
        # Update slug if name changed
        if "name" in update_data:
            new_slug = create_slug(update_data["name"])
            # Check if new slug conflicts (excluding current record)
            existing = db.query(models.EventType).filter(
                models.EventType.slug == new_slug,
                models.EventType.id != event_type_id
            ).first()
            
            if existing:
                counter = 1
                while existing:
                    test_slug = f"{new_slug}-{counter}"
                    existing = db.query(models.EventType).filter(
                        models.EventType.slug == test_slug,
                        models.EventType.id != event_type_id
                    ).first()
                    if not existing:
                        new_slug = test_slug
                        break
                    counter += 1
            
            event_type.slug = new_slug
        
        db.commit()
        db.refresh(event_type)
        
        return EventTypeResponse.from_orm(event_type)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/event-types/{event_type_id}")
async def delete_event_type(subdomain: str, event_type_id: int, db: Session = Depends(get_db)):
    """Delete an event type"""
    try:
        get_tenant_db(subdomain, db)
        
        event_type = db.query(models.EventType).filter(
            models.EventType.id == event_type_id
        ).first()
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        # Check if event type is being used in appointments
        appointments_count = db.query(models.Appointment).filter(
            models.Appointment.event_type_id == event_type_id
        ).count()
        
        if appointments_count > 0:
            # Soft delete - just deactivate
            event_type.is_active = False
            db.commit()
            return {"message": "Event type deactivated (has existing appointments)"}
        else:
            # Hard delete
            db.delete(event_type)
            db.commit()
            return {"message": "Event type deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/event-types/validate-availability")
async def validate_event_type_availability(subdomain: str, db: Session = Depends(get_db)):
    """ตรวจสอบและแก้ไข event types ที่มี availability_id ผิดพลาด"""
    try:
        get_tenant_db(subdomain, db)
        
        # หา event types ที่มี availability_id ที่ไม่มีอยู่จริงหรือถูก deactivate
        problematic_events = db.query(models.EventType).outerjoin(
            models.Availability, 
            models.EventType.availability_id == models.Availability.id
        ).filter(
            (models.Availability.id.is_(None)) |  # availability ไม่มีอยู่
            (models.Availability.is_active == False)  # หรือถูก deactivate
        ).all()
        
        if not problematic_events:
            return {"message": "All event types have valid availability assignments", "fixed_count": 0}
        
        # แก้ไขโดยกำหนด default availability
        default_availability_id = get_or_assign_default_availability(db)
        fixed_events = []
        
        for event in problematic_events:
            event.availability_id = default_availability_id
            fixed_events.append(event.name)
        
        db.commit()
        
        return {
            "message": f"Fixed {len(fixed_events)} event types with invalid availability",
            "fixed_count": len(fixed_events),
            "fixed_events": fixed_events,
            "assigned_to": "เวลาทำการเริ่มต้น"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))