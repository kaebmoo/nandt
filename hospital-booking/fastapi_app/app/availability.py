# fastapi_app/app/availability.py - Fixed version

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
    is_unavailable: bool = False
    custom_start_time: Optional[str] = None
    custom_end_time: Optional[str] = None
    reason: Optional[str] = None

class DateOverrideResponse(BaseModel):
    id: int
    date: datetime.datetime
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

def get_or_create_default_availability(db: Session) -> int:
    """สร้างหรือหา default availability template สำหรับใช้เป็น fallback"""
    
    # หา default template ที่มีอยู่แล้ว
    default_template = db.query(models.Availability).filter(
        models.Availability.name == "เวลาทำการเริ่มต้น",
        models.Availability.is_active == True
    ).first()
    
    if default_template:
        return default_template.id
    
    # สร้าง default template ใหม่ (จันทร์-ศุกร์ 08:30-16:30)
    default_schedule = [
        (1, "08:30", "16:30"),  # Monday
        (2, "08:30", "16:30"),  # Tuesday  
        (3, "08:30", "16:30"),  # Wednesday
        (4, "08:30", "16:30"),  # Thursday
        (5, "08:30", "16:30"),  # Friday
    ]
    
    created_ids = []
    for day_of_week, start_time_str, end_time_str in default_schedule:
        start_time = parse_time(start_time_str)
        end_time = parse_time(end_time_str)
        
        availability = models.Availability(
            name="เวลาทำการเริ่มต้น",
            description="เวลาทำการเริ่มต้น (สร้างอัตโนมัติ)",
            day_of_week=models.DayOfWeek(day_of_week),
            start_time=start_time,
            end_time=end_time,
            timezone="Asia/Bangkok",
            is_active=True
        )
        db.add(availability)
        db.flush()
        created_ids.append(availability.id)
    
    db.commit()
    return created_ids[0]  # Return first ID

# --- API Endpoints ---

@router.get("/availability", response_model=dict)
async def get_availability(subdomain: str, db: Session = Depends(get_db)):
    """Get availability schedules for a tenant"""
    try:
        get_tenant_db(subdomain, db)
        
        availabilities = db.query(models.Availability).order_by(models.Availability.created_at).all()
        
        # Convert to response format
        result = []
        for avail in availabilities:
            result.append({
                "id": avail.id,
                "name": avail.name,
                "description": avail.description,
                "day_of_week": avail.day_of_week.value if hasattr(avail.day_of_week, 'value') else avail.day_of_week,
                "start_time": format_time(avail.start_time),
                "end_time": format_time(avail.end_time),
                "timezone": avail.timezone,
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
        
        created_ids = []
        for day_of_week, slots in schedule_data.schedule.items():
            if not 0 <= int(day_of_week) <= 6:
                raise HTTPException(status_code=400, detail=f"Invalid day of week: {day_of_week}")
            for start_time_str, end_time_str in slots:
                start_time, end_time = parse_time(start_time_str), parse_time(end_time_str)
                if start_time >= end_time:
                    raise HTTPException(status_code=400, detail=f"Start time must be before end time for day {day_of_week}")
                availability = models.Availability(
                    name=schedule_data.name, description=schedule_data.description,
                    day_of_week=models.DayOfWeek(int(day_of_week)), start_time=start_time, end_time=end_time,
                    timezone=schedule_data.timezone, is_active=True)
                db.add(availability)
                db.flush()
                created_ids.append(availability.id)
        db.commit()
        return {"message": "Availability template created successfully", "ids": created_ids}
    except (ValueError, HTTPException) as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/availability/templates/{template_id}", response_model=dict)
async def update_availability_template(subdomain: str, template_id: int, schedule_data: WeeklySchedule, db: Session = Depends(get_db)):
    """Update an entire availability template."""
    get_tenant_db(subdomain, db)
    try:
        # หา template ที่จะแก้ไข
        original_template = db.query(models.Availability).filter(models.Availability.id == template_id).first()
        if not original_template:
            raise HTTPException(status_code=404, detail="Template not found.")
        
        original_name = original_template.name
        old_records = db.query(models.Availability).filter(models.Availability.name == original_name).all()
        
        new_schedule = schedule_data.schedule
        new_name, new_desc, new_tz = schedule_data.name, schedule_data.description, schedule_data.timezone

        # ตรวจสอบว่า template นี้ถูกใช้โดย event types หรือไม่
        old_record_ids = [r.id for r in old_records]
        events_using_template = db.query(models.EventType).filter(models.EventType.availability_id.in_(old_record_ids)).all()
        
        # สร้าง mapping ของ availability_id -> event types ที่ใช้
        usage_map = {}
        for event in events_using_template:
            if event.availability_id not in usage_map:
                usage_map[event.availability_id] = []
            usage_map[event.availability_id].append(event.name)

        # จัดกลุ่ม old records ตาม day_of_week
        old_slots_by_day = {day.value: [] for day in models.DayOfWeek}
        for record in old_records:
            old_slots_by_day[record.day_of_week.value].append(record)

        # จัดกลุ่ม new schedule ตาม day
        new_slots_by_day = {int(day): slots for day, slots in new_schedule.items()}

        # อัปเดตหรือสร้าง slots ใหม่ทีละวัน
        for day_int in range(7):
            old_day_slots = sorted(old_slots_by_day.get(day_int, []), key=lambda r: r.start_time)
            new_day_slots = sorted(new_slots_by_day.get(day_int, []), key=lambda t: parse_time(t[0]))

            # อัปเดต existing slots หรือสร้างใหม่
            for i, (start_str, end_str) in enumerate(new_day_slots):
                start_time, end_time = parse_time(start_str), parse_time(end_str)
                
                if i < len(old_day_slots):
                    # อัปเดต existing record
                    record_to_update = old_day_slots[i]
                    record_to_update.name = new_name
                    record_to_update.description = new_desc
                    record_to_update.timezone = new_tz
                    record_to_update.start_time = start_time
                    record_to_update.end_time = end_time
                else:
                    # สร้าง record ใหม่
                    new_record = models.Availability(
                        name=new_name, 
                        description=new_desc, 
                        day_of_week=models.DayOfWeek(day_int),
                        start_time=start_time, 
                        end_time=end_time, 
                        timezone=new_tz, 
                        is_active=True
                    )
                    db.add(new_record)

            # ลบ slots ที่เหลือ (ถ้า new slots น้อยกว่า old slots)
            if len(old_day_slots) > len(new_day_slots):
                for i in range(len(new_day_slots), len(old_day_slots)):
                    record_to_delete = old_day_slots[i]
                    
                    # ตรวจสอบว่า record นี้ถูกใช้โดย event type หรือไม่
                    if record_to_delete.id in usage_map:
                        event_names = ", ".join(usage_map[record_to_delete.id])
                        day_name = models.DayOfWeek(day_int).name.capitalize()
                        
                        raise HTTPException(
                            status_code=409, 
                            detail=f"Cannot remove time slot {day_name} ({format_time(record_to_delete.start_time)} - {format_time(record_to_delete.end_time)}) because it is used by event type(s): {event_names}. Please reassign them first."
                        )
                    
                    db.delete(record_to_delete)

        db.commit()
        return {"message": f"Template '{new_name}' updated successfully."}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/availability/templates/{template_id}")
async def delete_availability_template(subdomain: str, template_id: int, db: Session = Depends(get_db)):
    """Deletes an entire availability template with smart event type reassignment."""
    get_tenant_db(subdomain, db)
    try:
        # หา template ที่จะลบ
        template_to_delete = db.query(models.Availability).filter(models.Availability.id == template_id).first()
        if not template_to_delete:
            raise HTTPException(status_code=404, detail="Template not found.")
        
        template_name = template_to_delete.name
        records = db.query(models.Availability).filter(models.Availability.name == template_name).all()
        record_ids = [r.id for r in records]
        
        # หา event types ที่ใช้ template นี้
        conflicting_events = db.query(models.EventType).filter(models.EventType.availability_id.in_(record_ids)).all()
        
        if conflicting_events:
            # หา default availability หรือสร้างใหม่
            default_availability_id = get_or_create_default_availability(db)
            
            # ย้าย event types ที่ใช้ template นี้ไปใช้ default
            event_names = []
            for event in conflicting_events:
                event.availability_id = default_availability_id
                event_names.append(event.name)
            
            db.commit()
            
            # ลบ template
            for record in records:
                db.delete(record)
            
            db.commit()
            
            moved_events = ", ".join(set(event_names))
            return {
                "message": f"Template '{template_name}' deleted successfully. Event types ({moved_events}) have been moved to default availability template.",
                "moved_events": list(set(event_names))
            }
        else:
            # ไม่มี event types ใช้อยู่ ลบได้เลย
            for record in records:
                db.delete(record)
            
            db.commit()
            return {"message": f"Template '{template_name}' deleted successfully."}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/availability/templates", response_model=dict)
async def get_availability_templates(subdomain: str, db: Session = Depends(get_db)):
    """Get availability templates grouped by name"""
    try:
        get_tenant_db(subdomain, db)
        
        availabilities = db.query(models.Availability).filter(
            models.Availability.is_active == True
        ).order_by(models.Availability.created_at).all()
        
        templates = {}
        for avail in availabilities:
            template_name = avail.name or f"Template {avail.id}"
            
            if template_name not in templates:
                templates[template_name] = {
                    "id": avail.id,
                    "name": template_name,
                    "description": avail.description,
                    "days": [],
                    "timezone": avail.timezone
                }
            
            day_value = avail.day_of_week.value if hasattr(avail.day_of_week, 'value') else avail.day_of_week
            if day_value not in templates[template_name]["days"]:
                templates[template_name]["days"].append(day_value)
            
        return {"templates": list(templates.values())}
        
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
async def get_date_overrides(subdomain: str, db: Session = Depends(get_db)):
    """Get date overrides for a tenant"""
    try:
        get_tenant_db(subdomain, db)
        
        # ตรวจสอบว่า table date_overrides มีอยู่หรือไม่
        try:
            overrides = db.query(models.DateOverride).order_by(models.DateOverride.date).all()
        except Exception as table_error:
            # ถ้าไม่มี table date_overrides ให้สร้าง
            print(f"DateOverride table not found, creating: {table_error}")
            db.execute(text('''
                CREATE TABLE IF NOT EXISTS date_overrides (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    is_unavailable BOOLEAN DEFAULT false,
                    custom_start_time TIME,
                    custom_end_time TIME,
                    reason VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
            overrides = []
        
        # Convert to response format
        result = []
        for override in overrides:
            result.append({
                "id": override.id,
                "date": override.date.strftime("%Y-%m-%d"),
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
    """Create date override"""
    try:
        get_tenant_db(subdomain, db)
        
        # ตรวจสอบและสร้าง table ถ้าไม่มี
        try:
            db.execute(text('''
                CREATE TABLE IF NOT EXISTS date_overrides (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    is_unavailable BOOLEAN DEFAULT false,
                    custom_start_time TIME,
                    custom_end_time TIME,
                    reason VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            '''))
            db.commit()
        except Exception as create_error:
            print(f"Error creating date_overrides table: {create_error}")
        
        # Parse date
        try:
            override_date = datetime.datetime.strptime(override_data.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Parse times if provided
        custom_start_time = None
        custom_end_time = None
        
        if override_data.custom_start_time:
            custom_start_time = parse_time(override_data.custom_start_time)
        
        if override_data.custom_end_time:
            custom_end_time = parse_time(override_data.custom_end_time)
        
        # Validate time range if both provided
        if custom_start_time and custom_end_time and custom_start_time >= custom_end_time:
            raise HTTPException(status_code=400, detail="Start time must be before end time")
        
        # Create date override using SQLAlchemy model if available, otherwise use raw SQL
        try:
            override = models.DateOverride(
                date=override_date,
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
                    "is_unavailable": override.is_unavailable,
                    "custom_start_time": format_time(override.custom_start_time) if override.custom_start_time else None,
                    "custom_end_time": format_time(override.custom_end_time) if override.custom_end_time else None,
                    "reason": override.reason,
                    "created_at": override.created_at
                }
            }
        except Exception as model_error:
            # Fallback to raw SQL if model doesn't work
            print(f"Model creation failed, using raw SQL: {model_error}")
            db.rollback()
            
            # Use raw SQL as fallback
            sql = text("""
                INSERT INTO date_overrides (date, is_unavailable, custom_start_time, custom_end_time, reason, created_at)
                VALUES (:date, :is_unavailable, :custom_start_time, :custom_end_time, :reason, NOW())
                RETURNING id, date, is_unavailable, custom_start_time, custom_end_time, reason, created_at
            """)
            
            result = db.execute(sql, {
                'date': override_date,
                'is_unavailable': override_data.is_unavailable,
                'custom_start_time': custom_start_time,
                'custom_end_time': custom_end_time,
                'reason': override_data.reason
            })
            
            db.commit()
            row = result.fetchone()
            
            return {
                "message": "Date override created successfully",
                "date_override": {
                    "id": row[0],
                    "date": row[1].strftime("%Y-%m-%d"),
                    "is_unavailable": row[2],
                    "custom_start_time": format_time(row[3]) if row[3] else None,
                    "custom_end_time": format_time(row[4]) if row[4] else None,
                    "reason": row[5],
                    "created_at": row[6]
                }
            }
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/date-overrides/{override_id}")
async def delete_date_override(subdomain: str, override_id: int, db: Session = Depends(get_db)):
    """Delete date override"""
    try:
        get_tenant_db(subdomain, db)
        
        try:
            override = db.query(models.DateOverride).filter(
                models.DateOverride.id == override_id
            ).first()
            
            if not override:
                raise HTTPException(status_code=404, detail="Date override not found")
            
            db.delete(override)
            db.commit()
        except Exception as model_error:
            # Fallback to raw SQL
            print(f"Model deletion failed, using raw SQL: {model_error}")
            db.rollback()
            
            result = db.execute(text("DELETE FROM date_overrides WHERE id = :id"), {'id': override_id})
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Date override not found")
            
            db.commit()
        
        return {"message": "Date override deleted successfully"}
        
    except HTTPException:
        raise
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