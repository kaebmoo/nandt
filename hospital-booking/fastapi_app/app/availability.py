# fastapi_app/app/availability.py - Fixed version with template support

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field, validator, model_validator
from typing import List, Optional, Dict, Tuple, Any
import sys
import datetime
from datetime import time
import uuid

# Import database and models
from shared_db.database import SessionLocal
from shared_db import models

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

class TemplateSettings(BaseModel):
    template_type: str = "dedicated"
    max_concurrent_slots: int = 1
    requires_provider_assignment: bool = True

    @validator('max_concurrent_slots')
    def validate_slots(cls, value: int) -> int:
        if value is None or value < 1:
            raise ValueError("max_concurrent_slots must be at least 1")
        return value

    @validator('template_type')
    def validate_type(cls, value: str) -> str:
        allowed = {"dedicated", "shared", "pool"}
        if value not in allowed:
            raise ValueError(f"template_type must be one of {', '.join(sorted(allowed))}")
        return value


class WeeklySchedule(BaseModel):
    name: str
    description: Optional[str] = None
    timezone: str = "Asia/Bangkok"
    schedule: Dict[int, List[Tuple[str, str]]]
    settings: Optional[TemplateSettings] = None

class AvailabilityTemplate(BaseModel):
    id: int
    name: str
    description: Optional[str]
    days: List[int]
    template_type: str
    max_concurrent_slots: int
    requires_provider_assignment: bool
    timezone: str
    provider_count: int = 0
    active_schedule_count: int = 0
    capacity_rules: int = 0
    
    class Config:
        from_attributes = True


class TemplateProviderCreate(BaseModel):
    provider_id: int
    is_primary: bool = False
    can_auto_assign: bool = True
    priority: int = 0


class TemplateProviderUpdate(BaseModel):
    is_primary: Optional[bool]
    can_auto_assign: Optional[bool]
    priority: Optional[int]


class ProviderScheduleCreate(BaseModel):
    provider_id: int
    effective_date: str
    end_date: Optional[str] = None
    days_of_week: List[int] = Field(default_factory=list)
    recurrence_pattern: Optional[str] = None
    custom_start_time: Optional[str] = None
    custom_end_time: Optional[str] = None
    schedule_type: str = "regular"
    notes: Optional[str] = None

    @validator('days_of_week')
    def validate_days(cls, value: List[int]) -> List[int]:
        if not value:
            raise ValueError("days_of_week must contain at least one day")
        for day in value:
            if day < 0 or day > 6:
                raise ValueError("days_of_week must be between 0 and 6")
        return sorted(set(value))


class ProviderScheduleUpdate(BaseModel):
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    days_of_week: Optional[List[int]] = None
    recurrence_pattern: Optional[str] = None
    custom_start_time: Optional[str] = None
    custom_end_time: Optional[str] = None
    schedule_type: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class ResourceCapacityCreate(BaseModel):
    available_rooms: int = 1
    max_concurrent_appointments: Optional[int] = None
    day_of_week: Optional[int] = None
    specific_date: Optional[str] = None
    time_slot_start: Optional[str] = None
    time_slot_end: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True

    @validator('available_rooms')
    def validate_rooms(cls, value: int) -> int:
        if value < 1:
            raise ValueError("available_rooms must be at least 1")
        return value

    @validator('max_concurrent_appointments')
    def validate_capacity(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("max_concurrent_appointments must be positive")
        return value

    @validator('day_of_week')
    def validate_day(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and (value < 0 or value > 6):
            raise ValueError("day_of_week must be between 0 and 6")
        return value

    @model_validator(mode='after')
    def ensure_scope(cls, values: 'ResourceCapacityCreate') -> 'ResourceCapacityCreate':
        if values.specific_date is None and values.day_of_week is None:
            raise ValueError("Either specific_date or day_of_week must be provided")
        return values


class ResourceCapacityUpdate(BaseModel):
    available_rooms: Optional[int] = None
    max_concurrent_appointments: Optional[int] = None
    specific_date: Optional[str] = None
    day_of_week: Optional[int] = None
    time_slot_start: Optional[str] = None
    time_slot_end: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ProviderLeaveCreate(BaseModel):
    provider_id: int
    start_date: str
    end_date: str
    leave_type: Optional[str] = None
    reason: Optional[str] = None
    approved_by: Optional[str] = None
    is_approved: bool = False

    @validator('end_date')
    def validate_range(cls, end_date: str, values: Dict[str, Any]) -> str:
        start_date = values.get('start_date')
        if start_date and end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        return end_date


class ProviderLeaveUpdate(BaseModel):
    end_date: Optional[str]
    leave_type: Optional[str]
    reason: Optional[str]
    approved_by: Optional[str]
    is_approved: Optional[bool]

def parse_time(time_str: str) -> time:
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except:
        raise ValueError(f"Invalid time format: {time_str}")

def format_time(time_obj: time) -> str:
    return time_obj.strftime("%H:%M")


def parse_optional_time(value: Optional[str]) -> Optional[time]:
    if value is None:
        return None
    return parse_time(value)


def parse_date(date_str: str) -> datetime.date:
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {date_str}")


def to_day_enum(day_value: int) -> models.DayOfWeek:
    try:
        return models.DayOfWeek(day_value)
    except Exception:
        raise ValueError(f"Invalid day of week: {day_value}")

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
        
        # ตรวจสอบว่ามี template ชื่อเดียวกันแล้วหรือไม่ (optional warning)
        existing_template = db.query(models.AvailabilityTemplate).filter(
            models.AvailabilityTemplate.name == schedule_data.name,
            models.AvailabilityTemplate.is_active == True
        ).first()
        
        template_name = schedule_data.name
        if existing_template:
            # สร้างชื่อใหม่ที่ไม่ซ้ำ
            counter = 1
            while True:
                new_name = f"{schedule_data.name} ({counter})"
                exists = db.query(models.AvailabilityTemplate).filter(
                    models.AvailabilityTemplate.name == new_name,
                    models.AvailabilityTemplate.is_active == True
                ).first()
                if not exists:
                    template_name = new_name
                    break
                counter += 1
        
        # Apply template settings
        settings = schedule_data.settings or TemplateSettings()

        # สร้าง template
        template = models.AvailabilityTemplate(
            name=template_name,
            description=schedule_data.description,
            timezone=schedule_data.timezone,
            is_active=True,
            template_type=settings.template_type,
            max_concurrent_slots=settings.max_concurrent_slots,
            requires_provider_assignment=settings.requires_provider_assignment
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
        
        # Return response with information about any name changes
        response = {
            "message": "Availability template created successfully",
            "template_id": template.id,
            "template_name": template_name,
            "ids": created_ids
        }
        
        if template_name != schedule_data.name:
            response["warning"] = f"Template name was changed from '{schedule_data.name}' to '{template_name}' to avoid duplication"
        
        return response
    except Exception as e:
        db.rollback()
        # Better error handling for common database issues
        error_msg = str(e)
        if "duplicate key value" in error_msg.lower():
            raise HTTPException(
                status_code=409, 
                detail="A template with this name already exists. Please choose a different name."
            )
        elif "violates foreign key constraint" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail="Invalid reference to another table. Please check your data."
            )
        else:
            raise HTTPException(status_code=500, detail=f"Database error: {error_msg}")

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

        if schedule_data.settings:
            template.template_type = schedule_data.settings.template_type
            template.max_concurrent_slots = schedule_data.settings.max_concurrent_slots
            template.requires_provider_assignment = schedule_data.settings.requires_provider_assignment
        
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
                "timezone": template.timezone,
                "template_type": template.template_type,
                "max_concurrent_slots": template.max_concurrent_slots,
                "requires_provider_assignment": template.requires_provider_assignment,
                "provider_count": len(template.template_providers),
                "active_schedule_count": sum(1 for s in template.provider_schedules if s.is_active),
                "capacity_rules": len(template.resource_capacities)
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

        provider_assignments = []
        for assignment in template.template_providers:
            provider = assignment.provider
            provider_assignments.append({
                "assignment_id": assignment.id,
                "provider_id": provider.id if provider else None,
                "provider_name": provider.name if provider else None,
                "title": provider.title if provider else None,
                "department": provider.department if provider else None,
                "is_active": provider.is_active if provider else None,
                "is_primary": assignment.is_primary,
                "can_auto_assign": assignment.can_auto_assign,
                "priority": assignment.priority,
                "created_at": assignment.created_at.isoformat()
            })

        provider_schedules = []
        for schedule_row in template.provider_schedules:
            provider = schedule_row.provider
            provider_schedules.append({
                "schedule_id": schedule_row.id,
                "provider_id": provider.id if provider else None,
                "provider_name": provider.name if provider else None,
                "effective_date": schedule_row.effective_date.isoformat(),
                "end_date": schedule_row.end_date.isoformat() if schedule_row.end_date else None,
                "days_of_week": schedule_row.days_of_week,
                "recurrence_pattern": schedule_row.recurrence_pattern,
                "custom_start_time": format_time(schedule_row.custom_start_time) if schedule_row.custom_start_time else None,
                "custom_end_time": format_time(schedule_row.custom_end_time) if schedule_row.custom_end_time else None,
                "schedule_type": schedule_row.schedule_type,
                "is_active": schedule_row.is_active,
                "notes": schedule_row.notes,
                "updated_at": schedule_row.updated_at.isoformat() if schedule_row.updated_at else None
            })

        resource_capacities = []
        for capacity in template.resource_capacities:
            resource_capacities.append({
                "capacity_id": capacity.id,
                "specific_date": capacity.specific_date.isoformat() if capacity.specific_date else None,
                "day_of_week": capacity.day_of_week.value if capacity.day_of_week else None,
                "available_rooms": capacity.available_rooms,
                "max_concurrent_appointments": capacity.max_concurrent_appointments,
                "time_slot_start": format_time(capacity.time_slot_start) if capacity.time_slot_start else None,
                "time_slot_end": format_time(capacity.time_slot_end) if capacity.time_slot_end else None,
                "notes": capacity.notes,
                "is_active": capacity.is_active,
                "created_at": capacity.created_at.isoformat() if capacity.created_at else None
            })

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "timezone": template.timezone,
            "template_type": template.template_type,
            "max_concurrent_slots": template.max_concurrent_slots,
            "requires_provider_assignment": template.requires_provider_assignment,
            "schedule": schedule,
            "providers": provider_assignments,
            "provider_schedules": provider_schedules,
            "resource_capacities": resource_capacities
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Template Provider Assignments ---

@router.get("/availability/templates/{template_id}/providers", response_model=dict)
async def list_template_providers(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        template = db.query(models.AvailabilityTemplate).filter_by(id=template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        providers = []
        for assignment in template.template_providers:
            provider = assignment.provider
            providers.append({
                "assignment_id": assignment.id,
                "provider_id": provider.id if provider else None,
                "name": provider.name if provider else None,
                "title": provider.title if provider else None,
                "department": provider.department if provider else None,
                "is_active": provider.is_active if provider else None,
                "is_primary": assignment.is_primary,
                "can_auto_assign": assignment.can_auto_assign,
                "priority": assignment.priority,
                "created_at": assignment.created_at.isoformat()
            })

        return {"providers": providers}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/availability/templates/{template_id}/providers", response_model=dict)
async def add_template_provider(subdomain: str, template_id: int, payload: TemplateProviderCreate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        template = db.query(models.AvailabilityTemplate).filter_by(id=template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        provider = db.query(models.Provider).filter_by(id=payload.provider_id).first()
        if not provider or not provider.is_active:
            raise HTTPException(status_code=404, detail="Provider not found or inactive")

        existing_schedule = db.query(models.ProviderSchedule).filter_by(
            template_id=template_id,
            provider_id=payload.provider_id
        ).first()

        if existing_schedule:
            raise HTTPException(status_code=409, detail="Provider already has a schedule for this template")

        existing = db.query(models.TemplateProvider).filter_by(
            template_id=template_id,
            provider_id=payload.provider_id
        ).first()

        if existing:
            raise HTTPException(status_code=409, detail="Provider already assigned to this template")

        assignment = models.TemplateProvider(
            template_id=template_id,
            provider_id=payload.provider_id,
            is_primary=payload.is_primary,
            can_auto_assign=payload.can_auto_assign,
            priority=payload.priority
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)

        return {
            "message": "Provider added to template",
            "assignment_id": assignment.id
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/availability/templates/{template_id}/providers/{provider_id}", response_model=dict)
async def update_template_provider(subdomain: str, template_id: int, provider_id: int, payload: TemplateProviderUpdate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        assignment = db.query(models.TemplateProvider).filter_by(
            template_id=template_id,
            provider_id=provider_id
        ).first()

        if not assignment:
            raise HTTPException(status_code=404, detail="Provider assignment not found")

        if payload.is_primary is not None:
            assignment.is_primary = payload.is_primary
        if payload.can_auto_assign is not None:
            assignment.can_auto_assign = payload.can_auto_assign
        if payload.priority is not None:
            assignment.priority = payload.priority

        db.commit()

        return {"message": "Assignment updated"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/availability/templates/{template_id}/providers/{provider_id}", response_model=dict)
async def remove_template_provider(subdomain: str, template_id: int, provider_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        assignment = db.query(models.TemplateProvider).filter_by(
            template_id=template_id,
            provider_id=provider_id
        ).first()

        if not assignment:
            raise HTTPException(status_code=404, detail="Provider assignment not found")

        db.delete(assignment)
        db.commit()

        return {"message": "Provider removed from template"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


# --- Provider Schedules ---

@router.get("/availability/templates/{template_id}/schedules", response_model=dict)
async def list_provider_schedules(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        schedules = db.query(models.ProviderSchedule).filter_by(template_id=template_id).all()
        result = []
        for schedule in schedules:
            provider = schedule.provider
            result.append({
                "schedule_id": schedule.id,
                "provider_id": provider.id if provider else None,
                "provider_name": provider.name if provider else None,
                "effective_date": schedule.effective_date.isoformat(),
                "end_date": schedule.end_date.isoformat() if schedule.end_date else None,
                "days_of_week": schedule.days_of_week,
                "recurrence_pattern": schedule.recurrence_pattern,
                "custom_start_time": format_time(schedule.custom_start_time) if schedule.custom_start_time else None,
                "custom_end_time": format_time(schedule.custom_end_time) if schedule.custom_end_time else None,
                "schedule_type": schedule.schedule_type,
                "is_active": schedule.is_active,
                "notes": schedule.notes
            })

        return {"schedules": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/availability/templates/{template_id}/schedules", response_model=dict)
async def create_provider_schedule(subdomain: str, template_id: int, payload: ProviderScheduleCreate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        template = db.query(models.AvailabilityTemplate).filter_by(id=template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        provider = db.query(models.Provider).filter_by(id=payload.provider_id).first()
        if not provider or not provider.is_active:
            raise HTTPException(status_code=404, detail="Provider not found or inactive")

        schedule = models.ProviderSchedule(
            provider_id=payload.provider_id,
            template_id=template_id,
            effective_date=parse_date(payload.effective_date),
            end_date=parse_date(payload.end_date) if payload.end_date else None,
            days_of_week=payload.days_of_week,
            recurrence_pattern=payload.recurrence_pattern,
            custom_start_time=parse_optional_time(payload.custom_start_time),
            custom_end_time=parse_optional_time(payload.custom_end_time),
            schedule_type=payload.schedule_type,
            notes=payload.notes
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        return {
            "message": "Provider schedule created",
            "schedule_id": schedule.id
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/availability/templates/{template_id}/schedules/{schedule_id}", response_model=dict)
async def update_provider_schedule(subdomain: str, template_id: int, schedule_id: int, payload: ProviderScheduleUpdate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        schedule = db.query(models.ProviderSchedule).filter_by(id=schedule_id, template_id=template_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        if payload.effective_date:
            schedule.effective_date = parse_date(payload.effective_date)
        if payload.end_date is not None:
            schedule.end_date = parse_date(payload.end_date) if payload.end_date else None
        if payload.days_of_week is not None:
            if not payload.days_of_week:
                raise HTTPException(status_code=400, detail="days_of_week cannot be empty")
            schedule.days_of_week = sorted(set(payload.days_of_week))
        if payload.recurrence_pattern is not None:
            schedule.recurrence_pattern = payload.recurrence_pattern
        if payload.custom_start_time is not None:
            schedule.custom_start_time = parse_optional_time(payload.custom_start_time)
        if payload.custom_end_time is not None:
            schedule.custom_end_time = parse_optional_time(payload.custom_end_time)
        if payload.schedule_type is not None:
            schedule.schedule_type = payload.schedule_type
        if payload.is_active is not None:
            schedule.is_active = payload.is_active
        if payload.notes is not None:
            schedule.notes = payload.notes

        db.commit()

        return {"message": "Schedule updated"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/availability/templates/{template_id}/schedules/{schedule_id}", response_model=dict)
async def delete_provider_schedule(subdomain: str, template_id: int, schedule_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        schedule = db.query(models.ProviderSchedule).filter_by(id=schedule_id, template_id=template_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        db.delete(schedule)
        db.commit()

        return {"message": "Schedule deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


# --- Resource Capacity Rules ---

@router.get("/availability/templates/{template_id}/capacities", response_model=dict)
async def list_resource_capacities(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        capacities = db.query(models.ResourceCapacity).filter_by(template_id=template_id).all()
        result = []
        for capacity in capacities:
            result.append({
                "capacity_id": capacity.id,
                "specific_date": capacity.specific_date.isoformat() if capacity.specific_date else None,
                "day_of_week": capacity.day_of_week.value if capacity.day_of_week else None,
                "available_rooms": capacity.available_rooms,
                "max_concurrent_appointments": capacity.max_concurrent_appointments,
                "time_slot_start": format_time(capacity.time_slot_start) if capacity.time_slot_start else None,
                "time_slot_end": format_time(capacity.time_slot_end) if capacity.time_slot_end else None,
                "notes": capacity.notes,
                "is_active": capacity.is_active,
                "created_at": capacity.created_at.isoformat() if capacity.created_at else None
            })

        return {"capacities": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/availability/templates/{template_id}/capacities", response_model=dict)
async def create_resource_capacity(subdomain: str, template_id: int, payload: ResourceCapacityCreate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        template = db.query(models.AvailabilityTemplate).filter_by(id=template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        capacity = models.ResourceCapacity(
            template_id=template_id,
            specific_date=parse_date(payload.specific_date) if payload.specific_date else None,
            day_of_week=to_day_enum(payload.day_of_week) if payload.day_of_week is not None else None,
            available_rooms=payload.available_rooms,
            max_concurrent_appointments=payload.max_concurrent_appointments,
            time_slot_start=parse_optional_time(payload.time_slot_start),
            time_slot_end=parse_optional_time(payload.time_slot_end),
            notes=payload.notes,
            is_active=payload.is_active
        )
        db.add(capacity)
        db.commit()
        db.refresh(capacity)

        return {
            "message": "Resource capacity created",
            "capacity_id": capacity.id
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/availability/templates/{template_id}/capacities/{capacity_id}", response_model=dict)
async def update_resource_capacity(subdomain: str, template_id: int, capacity_id: int, payload: ResourceCapacityUpdate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        capacity = db.query(models.ResourceCapacity).filter_by(id=capacity_id, template_id=template_id).first()
        if not capacity:
            raise HTTPException(status_code=404, detail="Capacity rule not found")

        updated_fields = payload.model_fields_set

        if 'specific_date' in updated_fields:
            capacity.specific_date = parse_date(payload.specific_date) if payload.specific_date else None
        if 'day_of_week' in updated_fields:
            capacity.day_of_week = to_day_enum(payload.day_of_week) if payload.day_of_week is not None else None
        if 'available_rooms' in updated_fields:
            if payload.available_rooms is not None and payload.available_rooms < 1:
                raise HTTPException(status_code=400, detail="available_rooms must be at least 1")
            if payload.available_rooms is not None:
                capacity.available_rooms = payload.available_rooms
        if 'max_concurrent_appointments' in updated_fields:
            if payload.max_concurrent_appointments is not None and payload.max_concurrent_appointments < 1:
                raise HTTPException(status_code=400, detail="max_concurrent_appointments must be positive")
            capacity.max_concurrent_appointments = payload.max_concurrent_appointments
        if 'time_slot_start' in updated_fields or 'time_slot_end' in updated_fields:
            capacity.time_slot_start = parse_optional_time(payload.time_slot_start)
            capacity.time_slot_end = parse_optional_time(payload.time_slot_end)
        if 'notes' in updated_fields:
            capacity.notes = payload.notes
        if 'is_active' in updated_fields and payload.is_active is not None:
            capacity.is_active = payload.is_active

        if capacity.specific_date is None and capacity.day_of_week is None:
            raise HTTPException(status_code=400, detail="ต้องระบุวันที่เฉพาะเจาะจงหรือวันในสัปดาห์")

        db.commit()

        return {"message": "Capacity rule updated"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/availability/templates/{template_id}/capacities/{capacity_id}", response_model=dict)
async def delete_resource_capacity(subdomain: str, template_id: int, capacity_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        capacity = db.query(models.ResourceCapacity).filter_by(id=capacity_id, template_id=template_id).first()
        if not capacity:
            raise HTTPException(status_code=404, detail="Capacity rule not found")

        db.delete(capacity)
        db.commit()

        return {"message": "Capacity rule deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


# --- Provider Leaves ---

@router.get("/availability/providers/{provider_id}/leaves", response_model=dict)
async def list_provider_leaves(subdomain: str, provider_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        leaves = db.query(models.ProviderLeave).filter_by(provider_id=provider_id).order_by(models.ProviderLeave.start_date).all()
        result = []
        for leave in leaves:
            result.append({
                "leave_id": leave.id,
                "start_date": leave.start_date.isoformat(),
                "end_date": leave.end_date.isoformat(),
                "leave_type": leave.leave_type,
                "reason": leave.reason,
                "approved_by": leave.approved_by,
                "is_approved": leave.is_approved,
                "created_at": leave.created_at.isoformat() if leave.created_at else None
            })

        return {"leaves": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/availability/providers/{provider_id}/leaves", response_model=dict)
async def create_provider_leave(subdomain: str, provider_id: int, payload: ProviderLeaveCreate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        provider = db.query(models.Provider).filter_by(id=provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        if payload.provider_id != provider_id:
            raise HTTPException(status_code=400, detail="provider_id mismatch in payload")

        leave = models.ProviderLeave(
            provider_id=provider_id,
            start_date=parse_date(payload.start_date),
            end_date=parse_date(payload.end_date),
            leave_type=payload.leave_type,
            reason=payload.reason,
            approved_by=payload.approved_by,
            is_approved=payload.is_approved
        )
        db.add(leave)
        db.commit()
        db.refresh(leave)

        return {
            "message": "Provider leave created",
            "leave_id": leave.id
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/availability/providers/{provider_id}/leaves/{leave_id}", response_model=dict)
async def update_provider_leave(subdomain: str, provider_id: int, leave_id: int, payload: ProviderLeaveUpdate, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        leave = db.query(models.ProviderLeave).filter_by(id=leave_id, provider_id=provider_id).first()
        if not leave:
            raise HTTPException(status_code=404, detail="Leave record not found")

        if payload.end_date is not None:
            new_end = parse_date(payload.end_date)
            if new_end < leave.start_date:
                raise HTTPException(status_code=400, detail="end_date cannot be before start_date")
            leave.end_date = new_end
        if payload.leave_type is not None:
            leave.leave_type = payload.leave_type
        if payload.reason is not None:
            leave.reason = payload.reason
        if payload.approved_by is not None:
            leave.approved_by = payload.approved_by
        if payload.is_approved is not None:
            leave.is_approved = payload.is_approved

        db.commit()

        return {"message": "Leave record updated"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/availability/providers/{provider_id}/leaves/{leave_id}", response_model=dict)
async def delete_provider_leave(subdomain: str, provider_id: int, leave_id: int, db: Session = Depends(get_db)):
    try:
        get_tenant_db(subdomain, db)

        leave = db.query(models.ProviderLeave).filter_by(id=leave_id, provider_id=provider_id).first()
        if not leave:
            raise HTTPException(status_code=404, detail="Leave record not found")

        db.delete(leave)
        db.commit()

        return {"message": "Leave record deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

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
        if override_data.template_scope == 'template' and not override_data.template_id:
            raise HTTPException(status_code=400, detail="ต้องระบุเทมเพลตสำหรับวันพิเศษของเทมเพลต")

        if not override_data.is_unavailable:
            if not custom_start_time or not custom_end_time:
                raise HTTPException(status_code=400, detail="กรุณาระบุเวลาเริ่มและเวลาสิ้นสุดสำหรับเวลาพิเศษ")
        else:
            custom_start_time = None
            custom_end_time = None

        if custom_start_time and custom_end_time and custom_start_time >= custom_end_time:
            raise HTTPException(status_code=400, detail="Start time must be before end time")

        duplicate_query = db.query(models.DateOverride).filter(
            models.DateOverride.date == override_date,
            models.DateOverride.template_scope == override_data.template_scope
        )

        if override_data.template_scope == 'template':
            duplicate_query = duplicate_query.filter(models.DateOverride.template_id == override_data.template_id)
        else:
            duplicate_query = duplicate_query.filter(models.DateOverride.template_id.is_(None))

        existing_override = duplicate_query.first()
        if existing_override:
            raise HTTPException(status_code=409, detail="มีการตั้งค่าวันพิเศษในวันที่นี้อยู่แล้ว")
        
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