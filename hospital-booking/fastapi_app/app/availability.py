# fastapi_app/app/availability_api.py - Availability API endpoints

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
    name: str  # "จันทร์-ศุกร์ (08:30-16:30)"
    description: Optional[str] = None
    day_of_week: int  # 0=Sunday, 1=Monday, etc.
    start_time: str  # "08:30"
    end_time: str    # "17:00"
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
    date: str  # "2025-08-19"
    is_unavailable: bool = False
    custom_start_time: Optional[str] = None  # "09:00"
    custom_end_time: Optional[str] = None    # "17:00"
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

# New WeeklySchedule model
class WeeklySchedule(BaseModel):
    name: str
    description: Optional[str] = None
    timezone: str = "Asia/Bangkok"
    # A dictionary mapping day of week (int) to a list of time slots
    schedule: Dict[int, List[Tuple[str, str]]]

class AvailabilityTemplate(BaseModel):
    id: int
    name: str
    description: Optional[str]
    days: List[int]
    
    class Config:
        from_attributes = True

def parse_time(time_str: str) -> time:
    """Convert time string to time object"""
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except:
        raise ValueError(f"Invalid time format: {time_str}")

def format_time(time_obj: time) -> str:
    """Convert time object to string"""
    return time_obj.strftime("%H:%M")

# --- API Endpoints ---

@router.get("/availability", response_model=dict)
async def get_availability(
    subdomain: str,
    db: Session = Depends(get_db)
):
    """Get availability schedules for a tenant"""
    try:
        get_tenant_db(subdomain, db)
        
        availabilities = db.query(models.Availability).order_by(
            models.Availability.day_of_week, 
            models.Availability.start_time
        ).all()
        
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
        
        return {
            "availabilities": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Keep old single-day endpoint for backward compatibility
@router.post("/availability/single", response_model=dict)
async def create_single_availability(
    subdomain: str,
    availability_data: AvailabilityCreate,
    db: Session = Depends(get_db)
):
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

# New weekly schedule endpoint
@router.post("/availability", response_model=dict)
async def create_availability(
    subdomain: str,
    schedule_data: WeeklySchedule,
    db: Session = Depends(get_db)
):
    """Create availability template with weekly schedule"""
    try:
        get_tenant_db(subdomain, db)
        
        created_ids = []
        
        # Begin transaction
        for day_of_week, slots in schedule_data.schedule.items():
            # Validate day of week
            if not 0 <= day_of_week <= 6:
                raise HTTPException(status_code=400, detail=f"Invalid day of week: {day_of_week}")
                
            for start_time_str, end_time_str in slots:
                # Convert time strings to time objects
                start_time = parse_time(start_time_str)
                end_time = parse_time(end_time_str)
                
                # Validate time range
                if start_time >= end_time:
                    raise HTTPException(status_code=400, detail=f"Start time must be before end time for day {day_of_week}")
                
                # Create availability record
                availability = models.Availability(
                    name=schedule_data.name,
                    description=schedule_data.description,
                    day_of_week=models.DayOfWeek(day_of_week),
                    start_time=start_time,
                    end_time=end_time,
                    timezone=schedule_data.timezone,
                    is_active=True
                )
                
                db.add(availability)
                db.flush()  # Get ID without committing
                created_ids.append(availability.id)
                
        db.commit()
        return {"message": "Availability template created successfully", "ids": created_ids}
        
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/availability/templates", response_model=dict)
async def get_availability_templates(
    subdomain: str,
    db: Session = Depends(get_db)
):
    """Get availability templates grouped by name"""
    try:
        get_tenant_db(subdomain, db)
        
        availabilities = db.query(models.Availability).filter(
            models.Availability.is_active == True
        ).order_by(models.Availability.name, models.Availability.day_of_week).all()
        
        templates = {}
        for avail in availabilities:
            template_name = avail.name or f"Template {avail.id}"
            
            if template_name not in templates:
                templates[template_name] = {
                    "id": avail.id,  # Store the first ID found for the group
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
async def delete_availability(
    subdomain: str,
    availability_id: int,
    db: Session = Depends(get_db)
):
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
    db: Session = Depends(get_db)
):
    """Get date overrides for a tenant"""
    try:
        get_tenant_db(subdomain, db)
        
        overrides = db.query(models.DateOverride).order_by(models.DateOverride.date).all()
        
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
        
        return {
            "date_overrides": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/date-overrides", response_model=dict)
async def create_date_override(
    subdomain: str,
    override_data: DateOverrideCreate,
    db: Session = Depends(get_db)
):
    """Create date override"""
    try:
        get_tenant_db(subdomain, db)
        
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
        
        # Create date override
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
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/date-overrides/{override_id}")
async def delete_date_override(
    subdomain: str,
    override_id: int,
    db: Session = Depends(get_db)
):
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
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --- Providers (for dropdown) ---

@router.get("/providers", response_model=dict)
async def get_providers(
    subdomain: str,
    db: Session = Depends(get_db)
):
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
        
        return {
            "providers": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))