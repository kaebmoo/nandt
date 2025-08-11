# fastapi_app/app/availability.py - Fixed version with template support

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
import sys
import datetime
from datetime import time
import uuid

# Import database and models
from .database import SessionLocal
sys.path.append('flask_app/app')
import models

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["availability"])

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

# --- Pydantic Models ---
class AvailabilityCreate(BaseModel):
    name: str
    description: Optional[str] = None
    day_of_week: int
    start_time: str
    end_time: str
    timezone: str = "Asia/Bangkok"

class AvailabilityResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    day_of_week: int
    start_time: str
    end_time: str
    timezone: str
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class DateOverrideCreate(BaseModel):
    date: str
    template_id: Optional[int] = None
    template_scope: str = 'template'
    is_unavailable: bool = False
    custom_start_time: Optional[str] = None
    custom_end_time: Optional[str] = None
    reason: Optional[str] = None

class DateOverrideResponse(BaseModel):
    id: int
    date: datetime.datetime
    template_id: Optional[int]
    template_scope: str
    is_unavailable: bool
    custom_start_time: Optional[str]
    custom_end_time: Optional[str]
    reason: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class WeeklySchedule(BaseModel):
    name: str
    description: Optional[str] = None
    timezone: str = "Asia/Bangkok"
    schedule: Dict[int, List[Tuple[str, str]]]

class AvailabilityTemplate(BaseModel):
    id: int
    name: str
    description: Optional[str]
    days: List[int]
    
    class Config:
        from_attributes = True

def parse_time(time_str: str) -> time:
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except:
        raise ValueError(f"Invalid time format: {time_str}")

def format_time(time_obj: time) -> str:
    return time_obj.strftime("%H:%M")

def get_or_create_default_template(db: Session) -> int:
    """สร้างหรือหา default availability template"""
    
    # หา default template ที่มีอยู่แล้ว
    default_template = db.query(models.AvailabilityTemplate).filter(
        models.AvailabilityTemplate.name == "เวลาทำการเริ่มต้น",
        models.AvailabilityTemplate.is_active == True
    ).first()
    
    if default_template:
        return default_template.id
    
    # สร้าง template ใหม่
    template = models.AvailabilityTemplate(
        name="เวลาทำการเริ่มต้น",
        description="เวลาทำการเริ่มต้น (สร้างอัตโนมัติ)",
        timezone="Asia/Bangkok",
        is_active=True
    )
    db.add(template)
    db.flush()
    
    # สร้าง default schedule (จันทร์-ศุกร์ 08:30-16:30)
    default_schedule = [
        (1, "08:30", "16:30"),  # Monday
        (2, "08:30", "16:30"),  # Tuesday  
        (3, "08:30", "16:30"),  # Wednesday
        (4, "08:30", "16:30"),  # Thursday
        (5, "08:30", "16:30"),  # Friday
    ]
    
    for day_of_week, start_time_str, end_time_str in default_schedule:
        availability = models.Availability(
            template_id=template.id,
            day_of_week=models.DayOfWeek(day_of_week),
            start_time=parse_time(start_time_str),
            end_time=parse_time(end_time_str),
            is_active=True
        )
        db.add(availability)
    
    db.commit()
    return template.id

# --- API Endpoints ---

@router.get("/availability", response_model=dict)
async def get_availability(subdomain: str, db: Session = Depends(get_db)):
    """Get all availability records (backward compatibility)"""
    try:
        get_tenant_db(subdomain, db)
        
        # Query จาก availability_templates และ join กับ availabilities
        templates = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.is_active == True
        ).all()
        
        result = []
        for template in templates:
            for avail in template.availabilities:
                result.append({
                    "id": avail.id,
                    "name": template.name,  # ใช้ name จาก template
                    "description": template.description,
                    "day_of_week": avail.day_of_week.value if hasattr(avail.day_of_week, 'value') else avail.day_of_week,
                    "start_time": format_time(avail.start_time),
                    "end_time": format_time(avail.end_time),
                    "timezone": template.timezone,
                    "is_active": avail.is_active,
                    "created_at": avail.created_at
                })
        
        return {"availabilities": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/availability/single", response_model=dict)
async def create_single_availability(subdomain: str, availability_data: AvailabilityCreate, db: Session = Depends(get_db)):
    """Create single availability slot (backward compatibility)"""
    try:
        get_tenant_db(subdomain, db)
        
        # Convert time strings to time objects
        start_time = parse_time(availability_data.start_time)
        end_time = parse_time(availability_data.end_time)
        
        # Validate time range
        if start_time >= end_time:
            raise HTTPException(status_code=400, detail="Start time must be before end time")
        
        # Create availability
        availability = models.Availability(
            name=availability_data.name,
            description=availability_data.description,
            day_of_week=models.DayOfWeek(availability_data.day_of_week),
            start_time=start_time,
            end_time=end_time,
            timezone=availability_data.timezone,
            is_active=True
        )
        
        db.add(availability)
        db.commit()
        db.refresh(availability)
        
        return {
            "message": "Availability created successfully",
            "availability": {
                "id": availability.id,
                "name": availability.name,
                "description": availability.description,
                "day_of_week": availability.day_of_week.value,
                "start_time": format_time(availability.start_time),
                "end_time": format_time(availability.end_time),
                "timezone": availability.timezone,
                "is_active": availability.is_active,
                "created_at": availability.created_at
            }
        }
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/availability", response_model=dict)
async def create_availability(subdomain: str, schedule_data: WeeklySchedule, db: Session = Depends(get_db)):
    """Create availability template with weekly schedule"""
    try:
        get_tenant_db(subdomain, db)
        
        # สร้าง template ก่อน
        template = models.AvailabilityTemplate(
            name=schedule_data.name,
            description=schedule_data.description,
            timezone=schedule_data.timezone,
            is_active=True
        )
        db.add(template)
        db.flush()  # เพื่อได้ template.id
        
        # สร้าง availability records
        created_ids = []
        for day_of_week, slots in schedule_data.schedule.items():
            if not 0 <= int(day_of_week) <= 6:
                raise HTTPException(status_code=400, detail=f"Invalid day of week: {day_of_week}")
            
            for start_time_str, end_time_str in slots:
                start_time = parse_time(start_time_str)
                end_time = parse_time(end_time_str)
                
                if start_time >= end_time:
                    raise HTTPException(status_code=400, detail=f"Start time must be before end time for day {day_of_week}")
                
                availability = models.Availability(
                    template_id=template.id,  # ใช้ template_id
                    day_of_week=models.DayOfWeek(int(day_of_week)),
                    start_time=start_time,
                    end_time=end_time,
                    is_active=True
                )
                db.add(availability)
                db.flush()
                created_ids.append(availability.id)
        
        db.commit()
        return {
            "message": "Availability template created successfully",
            "template_id": template.id,
            "ids": created_ids
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/availability/templates/{template_id}", response_model=dict)
async def update_availability_template(subdomain: str, template_id: int, schedule_data: WeeklySchedule, db: Session = Depends(get_db)):
    """Update an entire availability template"""
    try:
        get_tenant_db(subdomain, db)
        
        # หา template
        template = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Update template info
        template.name = schedule_data.name
        template.description = schedule_data.description
        template.timezone = schedule_data.timezone
        
        # ตรวจสอบ event types ที่ใช้ template นี้
        events_using = db.query(models.EventType).filter(
            models.EventType.template_id == template_id
        ).all()
        
        # ลบ availabilities เดิมทั้งหมด
        db.query(models.Availability).filter(
            models.Availability.template_id == template_id
        ).delete()
        
        # สร้าง availabilities ใหม่
        for day_of_week, slots in schedule_data.schedule.items():
            for start_time_str, end_time_str in slots:
                availability = models.Availability(
                    template_id=template_id,
                    day_of_week=models.DayOfWeek(int(day_of_week)),
                    start_time=parse_time(start_time_str),
                    end_time=parse_time(end_time_str),
                    is_active=True
                )
                db.add(availability)
        
        db.commit()
        return {"message": f"Template '{schedule_data.name}' updated successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/availability/templates/{template_id}")
async def delete_availability_template(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    """Delete an entire availability template"""
    try:
        get_tenant_db(subdomain, db)
        
        # หา template
        template = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        template_name = template.name
        
        # หา event types ที่ใช้ template นี้
        events_using = db.query(models.EventType).filter(
            models.EventType.template_id == template_id
        ).all()
        
        if events_using:
            # สร้างหรือหา default template
            default_template_id = get_or_create_default_template(db)
            
            # ย้าย event types ไปใช้ default template
            event_names = []
            for event in events_using:
                event.template_id = default_template_id
                event_names.append(event.name)
            
            db.commit()
            
            # ลบ template (cascade จะลบ availabilities และ date_overrides)
            db.delete(template)
            db.commit()
            
            return {
                "message": f"Template '{template_name}' deleted successfully",
                "moved_events": event_names
            }
        else:
            # ลบ template ได้เลย
            db.delete(template)
            db.commit()
            return {"message": f"Template '{template_name}' deleted successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/availability/templates", response_model=dict)
async def get_availability_templates(subdomain: str, db: Session = Depends(get_db)):
    """Get all availability templates"""
    try:
        get_tenant_db(subdomain, db)
        
        templates = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.is_active == True
        ).order_by(models.AvailabilityTemplate.created_at).all()
        
        result = []
        for template in templates:
            # หาวันที่ template นี้มี
            days = set()
            for avail in template.availabilities:
                day_value = avail.day_of_week.value if hasattr(avail.day_of_week, 'value') else avail.day_of_week
                days.add(day_value)
            
            result.append({
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "days": sorted(list(days)),
                "timezone": template.timezone
            })
        
        return {"templates": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/availability/template/{template_id}/details", response_model=dict)
async def get_availability_template_details(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    """Get detailed schedule for a specific template"""
    try:
        get_tenant_db(subdomain, db)
        
        template = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # จัดกลุ่ม schedule ตาม day_of_week
        schedule = {}
        for avail in template.availabilities:
            if avail.is_active:
                day_num = avail.day_of_week.value if hasattr(avail.day_of_week, 'value') else avail.day_of_week
                day_str = str(day_num)
                
                if day_str not in schedule:
                    schedule[day_str] = []
                
                schedule[day_str].append({
                    'start': format_time(avail.start_time),
                    'end': format_time(avail.end_time)
                })
        
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "timezone": template.timezone,
            "schedule": schedule
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/availability/{availability_id}")
async def delete_availability(subdomain: str, availability_id: int, db: Session = Depends(get_db)):
    """Delete availability slot"""
    try:
        get_tenant_db(subdomain, db)
        
        availability = db.query(models.Availability).filter(
            models.Availability.id == availability_id
        ).first()
        
        if not availability:
            raise HTTPException(status_code=404, detail="Availability not found")
        
        db.delete(availability)
        db.commit()
        
        return {"message": "Availability deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- Date Overrides ---

@router.get("/date-overrides", response_model=dict)
async def get_date_overrides(
    subdomain: str, 
    template_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get date overrides for a tenant, optionally filtered by template_id"""
    try:
        get_tenant_db(subdomain, db)
        
        query = db.query(models.DateOverride)
        
        if template_id is not None:
            query = query.filter(models.DateOverride.template_id == template_id)
        
        overrides = query.order_by(models.DateOverride.date).all()
        
        result = []
        for override in overrides:
            result.append({
                "id": override.id,
                "date": override.date.strftime("%Y-%m-%d"),
                "template_id": override.template_id,
                "template_scope": override.template_scope,
                "is_unavailable": override.is_unavailable,
                "custom_start_time": format_time(override.custom_start_time) if override.custom_start_time else None,
                "custom_end_time": format_time(override.custom_end_time) if override.custom_end_time else None,
                "reason": override.reason,
                "created_at": override.created_at
            })
        
        return {"date_overrides": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/date-overrides", response_model=dict)
async def create_date_override(subdomain: str, override_data: DateOverrideCreate, db: Session = Depends(get_db)):
    """Create date override with template support"""
    try:
        get_tenant_db(subdomain, db)
        
        # Parse date
        override_date = datetime.datetime.strptime(override_data.date, "%Y-%m-%d").date()
        
        # Parse times if provided
        custom_start_time = parse_time(override_data.custom_start_time) if override_data.custom_start_time else None
        custom_end_time = parse_time(override_data.custom_end_time) if override_data.custom_end_time else None
        
        # Validate
        if custom_start_time and custom_end_time and custom_start_time >= custom_end_time:
            raise HTTPException(status_code=400, detail="Start time must be before end time")
        
        # Create override
        override = models.DateOverride(
            date=override_date,
            template_id=override_data.template_id,
            template_scope=override_data.template_scope,
            is_unavailable=override_data.is_unavailable,
            custom_start_time=custom_start_time,
            custom_end_time=custom_end_time,
            reason=override_data.reason
        )
        
        db.add(override)
        db.commit()
        db.refresh(override)
        
        return {
            "message": "Date override created successfully",
            "date_override": {
                "id": override.id,
                "date": override.date.strftime("%Y-%m-%d"),
                "template_id": override.template_id,
                "template_scope": override.template_scope,
                "is_unavailable": override.is_unavailable,
                "custom_start_time": format_time(override.custom_start_time) if override.custom_start_time else None,
                "custom_end_time": format_time(override.custom_end_time) if override.custom_end_time else None,
                "reason": override.reason,
                "created_at": override.created_at
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/date-overrides/{override_id}")
async def delete_date_override(subdomain: str, override_id: int, db: Session = Depends(get_db)):
    """Delete date override"""
    try:
        get_tenant_db(subdomain, db)
        
        override = db.query(models.DateOverride).filter(
            models.DateOverride.id == override_id
        ).first()
        
        if not override:
            raise HTTPException(status_code=404, detail="Date override not found")
        
        db.delete(override)
        db.commit()
        
        return {"message": "Date override deleted successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- Providers (for dropdown) ---

@router.get("/providers", response_model=dict)
async def get_providers(subdomain: str, db: Session = Depends(get_db)):
    """Get providers for dropdown"""
    try:
        get_tenant_db(subdomain, db)
        
        providers = db.query(models.Provider).filter(
            models.Provider.is_active == True
        ).order_by(models.Provider.name).all()
        
        result = []
        for provider in providers:
            result.append({
                "id": provider.id,
                "name": provider.name,
                "title": provider.title,
                "department": provider.department
            })
        
        return {"providers": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))