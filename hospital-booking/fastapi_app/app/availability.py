# fastapi_app/app/availability.py - Availability Management API

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date, time, timedelta
import calendar

# Import models
import sys
sys.path.append('flask_app/app')
import models

from .database import SessionLocal

router = APIRouter(prefix="/api/v1", tags=["availability"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Models
class AvailabilityCreate(BaseModel):
    provider_id: int
    event_type_id: int
    day_of_week: int  # 0=Sunday, 1=Monday, etc.
    start_time: str   # "09:00"
    end_time: str     # "17:00"
    timezone: str = "Asia/Bangkok"

class AvailabilityResponse(BaseModel):
    id: int
    provider_id: int
    event_type_id: int
    day_of_week: int
    start_time: str
    end_time: str
    timezone: str
    is_active: bool

class DateOverrideCreate(BaseModel):
    provider_id: int
    date: str  # "2025-08-14"
    is_unavailable: bool = False
    custom_start_time: Optional[str] = None  # "09:00"
    custom_end_time: Optional[str] = None    # "12:00"
    reason: Optional[str] = None

class EventTypeCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    duration_minutes: int = 15
    color: str = "#6366f1"
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    max_bookings_per_day: Optional[int] = None
    min_notice_hours: int = 4
    max_advance_days: int = 60

class ProviderCreate(BaseModel):
    name: str
    title: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    public_booking_url: Optional[str] = None
    bio: Optional[str] = None

class TimeSlot(BaseModel):
    start_time: str
    end_time: str
    available: bool
    booking_url: Optional[str] = None

class AvailableDay(BaseModel):
    date: str
    day_name: str
    slots: List[TimeSlot]

# Helper Functions
def get_tenant_db(db: Session, subdomain: str):
    """Switch to tenant schema"""
    schema_name = f"tenant_{subdomain}"
    db.execute(f'SET search_path TO "{schema_name}", public')
    return db

def time_to_str(t: time) -> str:
    """Convert time object to string"""
    return t.strftime("%H:%M")

def str_to_time(s: str) -> time:
    """Convert string to time object"""
    return datetime.strptime(s, "%H:%M").time()

def generate_time_slots(start_time: time, end_time: time, duration_minutes: int) -> List[dict]:
    """Generate available time slots"""
    slots = []
    current = datetime.combine(date.today(), start_time)
    end = datetime.combine(date.today(), end_time)
    
    while current + timedelta(minutes=duration_minutes) <= end:
        slot_end = current + timedelta(minutes=duration_minutes)
        slots.append({
            "start_time": current.strftime("%H:%M"),
            "end_time": slot_end.strftime("%H:%M"),
            "available": True
        })
        current = slot_end
    
    return slots

# API Endpoints

@router.post("/tenants/{subdomain}/providers")
def create_provider(
    subdomain: str,
    provider: ProviderCreate,
    db: Session = Depends(get_db)
):
    """สร้างผู้ให้บริการใหม่"""
    try:
        get_tenant_db(db, subdomain)
        
        # Check if public_booking_url is unique
        if provider.public_booking_url:
            existing = db.query(models.Provider).filter_by(
                public_booking_url=provider.public_booking_url
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail="Booking URL already exists")
        
        new_provider = models.Provider(**provider.dict())
        db.add(new_provider)
        db.commit()
        db.refresh(new_provider)
        
        return {"message": "Provider created successfully", "provider_id": new_provider.id}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{subdomain}/event-types")
def create_event_type(
    subdomain: str,
    event_type: EventTypeCreate,
    db: Session = Depends(get_db)
):
    """สร้างประเภทการนัดหมายใหม่"""
    try:
        get_tenant_db(db, subdomain)
        
        new_event_type = models.EventType(**event_type.dict())
        db.add(new_event_type)
        db.commit()
        db.refresh(new_event_type)
        
        return {"message": "Event type created successfully", "event_type_id": new_event_type.id}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{subdomain}/availability")
def create_availability(
    subdomain: str,
    availability: AvailabilityCreate,
    db: Session = Depends(get_db)
):
    """ตั้งค่าความพร้อมให้บริการ"""
    try:
        get_tenant_db(db, subdomain)
        
        new_availability = models.Availability(
            provider_id=availability.provider_id,
            event_type_id=availability.event_type_id,
            day_of_week=models.DayOfWeek(availability.day_of_week),
            start_time=str_to_time(availability.start_time),
            end_time=str_to_time(availability.end_time),
            timezone=availability.timezone
        )
        
        db.add(new_availability)
        db.commit()
        db.refresh(new_availability)
        
        return {"message": "Availability created successfully", "availability_id": new_availability.id}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/providers/{provider_id}/availability")
def get_provider_availability(
    subdomain: str,
    provider_id: int,
    db: Session = Depends(get_db)
):
    """ดูตารางความพร้อมของผู้ให้บริการ"""
    try:
        get_tenant_db(db, subdomain)
        
        availabilities = db.query(models.Availability).filter_by(
            provider_id=provider_id,
            is_active=True
        ).all()
        
        result = []
        for avail in availabilities:
            result.append({
                "id": avail.id,
                "day_of_week": avail.day_of_week.value,
                "day_name": avail.day_of_week.name.capitalize(),
                "start_time": time_to_str(avail.start_time),
                "end_time": time_to_str(avail.end_time),
                "event_type_id": avail.event_type_id,
                "timezone": avail.timezone
            })
        
        return {"availabilities": result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{subdomain}/date-overrides")
def create_date_override(
    subdomain: str,
    override: DateOverrideCreate,
    db: Session = Depends(get_db)
):
    """สร้างการปรับเปลี่ยนตารางในวันเฉพาะ"""
    try:
        get_tenant_db(db, subdomain)
        
        override_date = datetime.strptime(override.date, "%Y-%m-%d").date()
        
        new_override = models.DateOverride(
            provider_id=override.provider_id,
            date=override_date,
            is_unavailable=override.is_unavailable,
            custom_start_time=str_to_time(override.custom_start_time) if override.custom_start_time else None,
            custom_end_time=str_to_time(override.custom_end_time) if override.custom_end_time else None,
            reason=override.reason
        )
        
        db.add(new_override)
        db.commit()
        db.refresh(new_override)
        
        return {"message": "Date override created successfully", "override_id": new_override.id}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/available-slots")
def get_available_slots(
    subdomain: str,
    provider_id: int,
    event_type_id: int,
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    days: int = Query(30, description="Number of days to fetch"),
    db: Session = Depends(get_db)
):
    """ดูช่วงเวลาที่ว่างสำหรับการจอง"""
    try:
        get_tenant_db(db, subdomain)
        
        # Get provider and event type
        provider = db.query(models.Provider).filter_by(id=provider_id).first()
        event_type = db.query(models.EventType).filter_by(id=event_type_id).first()
        
        if not provider or not event_type:
            raise HTTPException(status_code=404, detail="Provider or event type not found")
        
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        available_days = []
        
        for i in range(days):
            current_date = start + timedelta(days=i)
            day_of_week = current_date.weekday()  # 0=Monday
            day_of_week_sunday = (day_of_week + 1) % 7  # Convert to 0=Sunday
            
            # Get regular availability for this day
            availability = db.query(models.Availability).filter_by(
                provider_id=provider_id,
                event_type_id=event_type_id,
                day_of_week=models.DayOfWeek(day_of_week_sunday),
                is_active=True
            ).first()
            
            if not availability:
                continue
            
            # Check for date overrides
            date_override = db.query(models.DateOverride).filter_by(
                provider_id=provider_id,
                date=current_date
            ).first()
            
            # Skip if unavailable
            if date_override and date_override.is_unavailable:
                continue
            
            # Use override times if available
            if date_override and date_override.custom_start_time:
                start_time = date_override.custom_start_time
                end_time = date_override.custom_end_time
            else:
                start_time = availability.start_time
                end_time = availability.end_time
            
            # Generate time slots
            slots = generate_time_slots(start_time, end_time, event_type.duration_minutes)
            
            # Check existing appointments to mark slots as unavailable
            existing_appointments = db.query(models.Appointment).filter(
                models.Appointment.provider_id == provider_id,
                models.Appointment.start_time >= datetime.combine(current_date, time.min),
                models.Appointment.start_time < datetime.combine(current_date + timedelta(days=1), time.min),
                models.Appointment.status.in_(['confirmed', 'rescheduled'])
            ).all()
            
            booked_times = {appt.start_time.strftime("%H:%M") for appt in existing_appointments}
            
            for slot in slots:
                if slot["start_time"] in booked_times:
                    slot["available"] = False
                else:
                    # Generate booking URL
                    slot["booking_url"] = f"/book/{provider.public_booking_url}/{event_type.slug}?date={current_date}&time={slot['start_time']}"
            
            available_days.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "day_name": calendar.day_name[current_date.weekday()],
                "slots": slots
            })
        
        return {"available_days": available_days}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/providers")
def list_providers(
    subdomain: str,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """รายการผู้ให้บริการ"""
    try:
        get_tenant_db(db, subdomain)
        
        query = db.query(models.Provider)
        if active_only:
            query = query.filter_by(is_active=True)
        
        providers = query.all()
        
        result = []
        for provider in providers:
            result.append({
                "id": provider.id,
                "name": provider.name,
                "title": provider.title,
                "department": provider.department,
                "public_booking_url": provider.public_booking_url,
                "bio": provider.bio,
                "is_active": provider.is_active
            })
        
        return {"providers": result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/event-types")
def list_event_types(
    subdomain: str,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """รายการประเภทการนัดหมาย"""
    try:
        get_tenant_db(db, subdomain)
        
        query = db.query(models.EventType)
        if active_only:
            query = query.filter_by(is_active=True)
        
        event_types = query.all()
        
        result = []
        for et in event_types:
            result.append({
                "id": et.id,
                "name": et.name,
                "slug": et.slug,
                "description": et.description,
                "duration_minutes": et.duration_minutes,
                "color": et.color,
                "is_active": et.is_active
            })
        
        return {"event_types": result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))