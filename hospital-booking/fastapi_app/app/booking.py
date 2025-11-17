# fastapi_app/app/booking.py - Complete Booking API

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, List, Dict, Literal
from datetime import datetime, timedelta, date, time
import string
import random
import sys
import logging

# Import database and models
from shared_db.database import SessionLocal
from shared_db import models

# Setup logging
logger = logging.getLogger(__name__)

class AppointmentSearch(BaseModel):
    search_type: Literal['email', 'phone', 'reference']
    search_value: str

router = APIRouter(prefix="/api/v1/tenants/{subdomain}", tags=["booking"])

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tenant_db(subdomain: str):
    """สร้าง dependency ที่ return function สำหรับ FastAPI"""
    def _get_db():
        db = SessionLocal()
        try:
            schema_name = f"tenant_{subdomain}"
            # Set search_path ทันที
            db.execute(text(f'SET search_path TO "{schema_name}", public'))
            db.commit()  # Commit การ set search_path
            yield db
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Tenant not found: {subdomain}")
        finally:
            db.close()
    return _get_db

# --- Pydantic Models ---
class TimeSlot(BaseModel):
    time: str  # "09:00"
    available: bool
    remaining_slots: int = 1
    total_capacity: int = 1
    available_provider_ids: Optional[List[int]] = None
    provider_pool_ids: Optional[List[int]] = None
    unavailable_reason: Optional[str] = None

class AvailabilityResponse(BaseModel):
    date: str
    slots: List[TimeSlot]
    event_type: Dict
    provider: Optional[Dict] = None
    template_id: Optional[int] = None
    template_type: Optional[str] = None
    requires_provider_assignment: Optional[bool] = None
    message: Optional[str] = None
    is_holiday: Optional[bool] = None

class BookingCreate(BaseModel):
    event_type_id: int
    provider_id: Optional[int] = None
    date: str  # "2025-08-15"
    time: str  # "09:00"
    guest_name: str
    guest_email: Optional[EmailStr] = None
    guest_phone: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('guest_email', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '':
            return None
        return v
    
    @field_validator('guest_phone', mode='before')
    @classmethod
    def phone_empty_str_to_none(cls, v):
        if v == '':
            return None
        return v
    
    @model_validator(mode='after')
    def check_contact_info(self):
        if not self.guest_email and not self.guest_phone:
            raise ValueError('ต้องระบุ email หรือเบอร์โทรอย่างน้อย 1 อย่าง')
        return self

class BookingResponse(BaseModel):
    success: bool
    booking_reference: str
    appointment_datetime: str
    guest_name: str
    event_type_name: str
    provider_name: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    message: str

class RescheduleRequest(BaseModel):
    booking_reference: str
    new_date: str
    new_time: str
    provider_id: Optional[int] = None
    reason: Optional[str] = None


class RestoreRequest(BaseModel):
    booking_reference: str
    reason: Optional[str] = None

class EventTypeDetail(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    color: Optional[str] = None
    template_id: Optional[int] = None
    # เพิ่ม field อื่นๆ ที่จำเป็นสำหรับหน้า reschedule
    max_advance_days: Optional[int] = None
    min_notice_hours: int

class CancelRequest(BaseModel):
    booking_reference: str
    reason: Optional[str] = None

# --- Helper Functions ---
def generate_booking_reference():
    """Generate booking reference like VN-A1B2C3"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"VN-{letters[0]}{numbers[0]}{letters[1]}{numbers[1]}{letters[2]}{numbers[2]}"

def parse_datetime(date_str: str, time_str: str) -> datetime:
    """Parse date and time strings to datetime"""
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

def format_time(time_obj: time) -> str:
    """Format time object to string"""
    return time_obj.strftime("%H:%M")

def generate_time_slots(start_time: time, end_time: time, duration_minutes: int) -> List[str]:
    """Generate time slots between start and end time"""
    slots = []
    current = datetime.combine(date.today(), start_time)
    end = datetime.combine(date.today(), end_time)
    delta = timedelta(minutes=duration_minutes)
    
    while current + delta <= end:
        slots.append(current.strftime("%H:%M"))
        current += delta
    
    return slots


def convert_python_weekday(python_weekday: int) -> int:
    """Convert Python weekday (0=Monday) to DayOfWeek enum value (0=Sunday)."""
    return 0 if python_weekday == 6 else python_weekday + 1


def resolve_resource_limits(template: models.AvailabilityTemplate, target_date: date) -> Dict[str, Optional[int]]:
    """Determine capacity limits based on template settings and resource rules."""
    # Default to 999 (virtually unlimited) if not set, allowing maximum flexibility
    rooms_limit = template.max_concurrent_slots if template.max_concurrent_slots else 999
    rule_limit = None

    specific_rules = [r for r in template.resource_capacities if r.is_active and r.specific_date == target_date]
    if specific_rules:
        # Use the rule with the smallest capacity constraint
        rule = min(specific_rules, key=lambda r: r.available_rooms)
        rooms_limit = min(rooms_limit, rule.available_rooms)
        if rule.max_concurrent_appointments:
            rule_limit = rule.max_concurrent_appointments
    else:
        target_day = convert_python_weekday(target_date.weekday())
        day_rules = [r for r in template.resource_capacities if r.is_active and r.day_of_week and r.day_of_week.value == target_day]
        if day_rules:
            rule = min(day_rules, key=lambda r: r.available_rooms)
            rooms_limit = min(rooms_limit, rule.available_rooms)
            if rule.max_concurrent_appointments:
                rule_limit = rule.max_concurrent_appointments

    return {
        "rooms_limit": rooms_limit,
        "max_concurrent": rule_limit
    }


def get_active_holiday(db: Session, target_date: date) -> Optional[models.Holiday]:
    return db.query(models.Holiday).filter(
        models.Holiday.date == target_date,
        models.Holiday.is_active == True
    ).first()


def get_relevant_date_override(db: Session, template_id: Optional[int], target_date: date) -> Optional[models.DateOverride]:
    template_override = None
    if template_id is not None:
        template_override = db.query(models.DateOverride).filter(
            models.DateOverride.date == target_date,
            models.DateOverride.template_id == template_id
        ).order_by(models.DateOverride.id.desc()).first()

    if template_override:
        return template_override

    return db.query(models.DateOverride).filter(
        models.DateOverride.date == target_date,
        models.DateOverride.template_scope == 'global'
    ).order_by(models.DateOverride.id.desc()).first()


def is_slot_blocked_by_override(
    override: Optional[models.DateOverride],
    target_date: date,
    slot_start: datetime,
    slot_end: datetime
) -> bool:
    if not override:
        return False

    if override.is_unavailable:
        return True

    if override.custom_start_time and override.custom_end_time:
        override_start = datetime.combine(target_date, override.custom_start_time)
        override_end = datetime.combine(target_date, override.custom_end_time)
        if slot_start < override_start or slot_end > override_end:
            return True

    return False


def collect_available_providers(
    db: Session,
    template: models.AvailabilityTemplate,
    target_date: date,
    slot_start: datetime,
    slot_end: datetime,
    date_override: Optional[models.DateOverride] = None
) -> List[int]:
    """Return provider IDs available for the given slot."""
    print(f"\n{'='*80}")
    print(f"🔍 collect_available_providers DEBUG")
    print(f"{'='*80}")
    print(f"Template ID: {template.id}, Target Date: {target_date}")
    print(f"Slot: {slot_start.time()} - {slot_end.time()}")

    if is_slot_blocked_by_override(date_override, target_date, slot_start, slot_end):
        print("❌ Slot blocked by date override")
        return []

    target_day = convert_python_weekday(target_date.weekday())
    print(f"Target day (converted): {target_day} (Python weekday: {target_date.weekday()})")

    schedules = db.query(models.ProviderSchedule).filter(
        models.ProviderSchedule.template_id == template.id,
        models.ProviderSchedule.is_active == True,
        models.ProviderSchedule.effective_date <= target_date,
        (models.ProviderSchedule.end_date.is_(None) | (models.ProviderSchedule.end_date >= target_date))
    ).all()

    print(f"\n📋 Found {len(schedules)} provider schedules for template {template.id}")

    available_ids = []
    for schedule in schedules:
        provider = schedule.provider
        print(f"\n--- Checking Schedule ID {schedule.id} ---")
        print(f"Provider: [{schedule.provider_id}] {provider.name if provider else 'None'}")

        if not provider or not provider.is_active:
            print(f"❌ Provider inactive or missing")
            continue

        days = schedule.days_of_week or []
        print(f"Days of week: {days} (type: {type(days)})")
        print(f"Checking if {target_day} in {days}: {target_day in days}")

        if target_day not in days:
            print(f"❌ Target day {target_day} not in schedule days {days}")
            continue

        # Respect custom time windows if provided
        if schedule.custom_start_time:
            schedule_start = datetime.combine(target_date, schedule.custom_start_time)
            print(f"Custom start time: {schedule.custom_start_time}, slot start: {slot_start.time()}")
            if slot_start < schedule_start:
                print(f"❌ Slot start {slot_start.time()} before custom start {schedule.custom_start_time}")
                continue
        if schedule.custom_end_time:
            schedule_end = datetime.combine(target_date, schedule.custom_end_time)
            print(f"Custom end time: {schedule.custom_end_time}, slot end: {slot_end.time()}")
            if slot_end > schedule_end:
                print(f"❌ Slot end {slot_end.time()} after custom end {schedule.custom_end_time}")
                continue

        # Exclude providers on leave
        leave_exists = db.query(models.ProviderLeave).filter(
            models.ProviderLeave.provider_id == provider.id,
            models.ProviderLeave.start_date <= target_date,
            models.ProviderLeave.end_date >= target_date,
        ).first()
        if leave_exists:
            print(f"❌ Provider on leave: {leave_exists.start_date} to {leave_exists.end_date}")
            continue

        print(f"✅ Provider {provider.id} ({provider.name}) is available")
        available_ids.append(provider.id)

    print(f"\n{'='*80}")
    print(f"📊 RESULT: {len(available_ids)} providers available: {available_ids}")
    print(f"{'='*80}\n")
    return available_ids


def fetch_slot_bookings(
    db: Session,
    event_type_id: int,
    slot_start: datetime,
    slot_end: datetime,
    provider_ids: Optional[List[int]] = None
) -> List[models.Appointment]:
    query = db.query(models.Appointment).filter(
        models.Appointment.event_type_id == event_type_id,
        models.Appointment.status.in_(['confirmed', 'pending']),
        models.Appointment.start_time < slot_end,
        models.Appointment.end_time > slot_start
    )

    if provider_ids is not None:
        query = query.filter(models.Appointment.provider_id.in_(provider_ids))

    return query.all()


def select_auto_provider(template: models.AvailabilityTemplate, available_provider_ids: List[int]) -> Optional[int]:
    """Choose provider based on template assignments and priority."""
    prioritized = sorted(
        template.template_providers,
        key=lambda assignment: (
            0 if assignment.is_primary else 1,
            assignment.priority,
            assignment.id
        )
    )

    for assignment in prioritized:
        if assignment.provider_id in available_provider_ids:
            return assignment.provider_id

    return available_provider_ids[0] if available_provider_ids else None


def ensure_slot_capacity(
    db: Session,
    event_type: models.EventType,
    template: models.AvailabilityTemplate,
    slot_start: datetime,
    slot_end: datetime,
    provider_id: Optional[int] = None
) -> Optional[int]:
    """Validate slot availability and return provider assignment (auto or requested)."""
    if template is None:
        raise HTTPException(status_code=400, detail="บริการนี้ยังไม่ได้ตั้งค่าเวลาทำการ")

    target_date = slot_start.date()

    holiday = get_active_holiday(db, target_date)
    if holiday:
        detail = holiday.description or f"ปิดทำการ: {holiday.name}"
        raise HTTPException(status_code=409, detail=detail)

    date_override = get_relevant_date_override(db, template.id if template else None, target_date)
    if is_slot_blocked_by_override(date_override, target_date, slot_start, slot_end):
        detail = date_override.reason if date_override else None
        raise HTTPException(status_code=409, detail=detail or "ช่วงเวลานี้ไม่เปิดให้บริการ")

    capacity_info = resolve_resource_limits(template, target_date)
    capacity_limit = capacity_info["rooms_limit"] or 1
    if capacity_info["max_concurrent"]:
        capacity_limit = min(capacity_limit, capacity_info["max_concurrent"])

    available_provider_ids: Optional[List[int]] = None

    if template.requires_provider_assignment:
        available_provider_ids = collect_available_providers(
            db,
            template,
            target_date,
            slot_start,
            slot_end,
            date_override
        )
        if not available_provider_ids:
            raise HTTPException(status_code=409, detail="ไม่มีผู้ให้บริการว่างในช่วงเวลานี้")

        if provider_id:
            if provider_id not in available_provider_ids:
                raise HTTPException(status_code=409, detail="ผู้ให้บริการที่เลือกไม่ว่างในช่วงเวลานี้")
            available_provider_ids = [provider_id]

        capacity_limit = min(capacity_limit, len(available_provider_ids))

    else:
        provider_pool_ids = collect_available_providers(
            db,
            template,
            target_date,
            slot_start,
            slot_end,
            date_override
        )

        if not provider_pool_ids:
            raise HTTPException(status_code=409, detail="ไม่มีผู้ให้บริการว่างในช่วงเวลานี้")

        capacity_limit = min(capacity_limit, len(provider_pool_ids))

        if provider_id:
            if provider_id not in provider_pool_ids:
                raise HTTPException(status_code=409, detail="ผู้ให้บริการที่เลือกไม่ว่างในช่วงเวลานี้")
            provider = db.query(models.Provider).filter_by(id=provider_id, is_active=True).first()
            if not provider:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ให้บริการที่เลือกหรือไม่พร้อมใช้งาน")

        available_provider_ids = provider_pool_ids

    bookings = fetch_slot_bookings(db, event_type.id, slot_start, slot_end)

    assigned_provider_id = provider_id

    if template.requires_provider_assignment:
        booked_provider_ids = {appt.provider_id for appt in bookings if appt.provider_id}
        unassigned_bookings = len([appt for appt in bookings if not appt.provider_id])

        available_provider_ids = available_provider_ids or []
        remaining_providers = [pid for pid in available_provider_ids if pid not in booked_provider_ids]
        occupied_slots = len(booked_provider_ids) + unassigned_bookings
        remaining_capacity = max(capacity_limit - occupied_slots, 0)

        if provider_id:
            if provider_id not in remaining_providers or remaining_capacity == 0:
                raise HTTPException(status_code=409, detail="ผู้ให้บริการที่เลือกถูกจองแล้วในช่วงเวลานี้")
            assigned_provider_id = provider_id
        else:
            if remaining_capacity == 0 or not remaining_providers:
                raise HTTPException(status_code=409, detail="ช่วงเวลานี้ถูกจองเต็มแล้ว")
            assigned_provider_id = select_auto_provider(template, remaining_providers)
            if assigned_provider_id is None:
                raise HTTPException(status_code=409, detail="ไม่สามารถกำหนดผู้ให้บริการอัตโนมัติได้")

    else:
        bookings_within_slot = bookings
        if len(bookings_within_slot) >= capacity_limit:
            raise HTTPException(status_code=409, detail="ช่วงเวลานี้ถูกจองเต็มแล้ว")

        if provider_id and any(appt.provider_id == provider_id for appt in bookings_within_slot):
            raise HTTPException(status_code=409, detail="ผู้ให้บริการที่เลือกถูกจองแล้วในช่วงเวลานี้")

        provider_pool_ids = provider_pool_ids or []
        booked_provider_ids = [appt.provider_id for appt in bookings_within_slot if appt.provider_id]
        unassigned_bookings = len([appt for appt in bookings_within_slot if not appt.provider_id])
        remaining_pool = [pid for pid in provider_pool_ids if pid not in booked_provider_ids]

        if unassigned_bookings >= len(remaining_pool):
            raise HTTPException(status_code=409, detail="ช่วงเวลานี้ถูกจองเต็มแล้ว")

        available_after_unassigned = remaining_pool[unassigned_bookings:]

        remaining_capacity = max(capacity_limit - len(bookings_within_slot), 0)
        if remaining_capacity == 0 or not available_after_unassigned:
            raise HTTPException(status_code=409, detail="ช่วงเวลานี้ถูกจองเต็มแล้ว")

        if provider_id:
            if provider_id not in available_after_unassigned:
                raise HTTPException(status_code=409, detail="ผู้ให้บริการที่เลือกถูกจองแล้วในช่วงเวลานี้")
            assigned_provider_id = provider_id
        else:
            assigned_provider_id = select_auto_provider(template, available_after_unassigned) if available_after_unassigned else None
            if assigned_provider_id is None:
                raise HTTPException(status_code=409, detail="ไม่สามารถกำหนดผู้ให้บริการอัตโนมัติได้")

    return assigned_provider_id

# --- Main API Endpoints ---

@router.get("/event-types/{event_type_id}", response_model=EventTypeDetail)
async def get_event_type_details(
    subdomain: str,
    event_type_id: int,
    db: Session = Depends(get_db)
):
    """Get details for a single event type."""
    # Set search_path for the correct tenant
    schema_name = f"tenant_{subdomain}"
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {subdomain}")

    # Query for the event type
    event_type = db.query(models.EventType).filter(
        models.EventType.id == event_type_id,
        models.EventType.is_active == True
    ).first()

    if not event_type:
        raise HTTPException(status_code=404, detail="Event type not found or is not active")

    return event_type

@router.get("/booking/availability/{event_type_id}")
async def get_booking_availability(
    subdomain: str,
    event_type_id: int,
    date: str,
    provider_id: Optional[int] = None,
    db: Session = Depends(get_db)  
):
    # Set search_path
    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()

    try:
        # 1. Get event type with template
        event_type = db.query(models.EventType).filter_by(
            id=event_type_id,
            is_active=True
        ).first()
        
        if not event_type:
            raise HTTPException(404, "Event type not found or inactive")
        
        # 2. Parse date and prepare response metadata
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.now().date()
        template = event_type.availability_template

        event_type_info = {
            "id": event_type.id,
            "name": event_type.name,
            "duration": event_type.duration_minutes,
            "buffer_before": event_type.buffer_before_minutes,
            "buffer_after": event_type.buffer_after_minutes
        }

        response_data = {
            "date": date,
            "slots": [],
            "event_type": event_type_info,
            "template_id": template.id if template else None,
            "template_type": template.template_type if template else None,
            "requires_provider_assignment": template.requires_provider_assignment if template else None,
            "message": None,
            "is_holiday": False
        }

        # 2.5 Check for holidays first
        holiday = get_active_holiday(db, target_date)

        if holiday:
            response_data["message"] = holiday.description or f"ปิดทำการ: {holiday.name}"
            response_data["is_holiday"] = True
            return AvailabilityResponse(**response_data)

        if target_date < today:
            response_data["message"] = "ไม่สามารถจองวันที่ผ่านมาแล้ว"
            return AvailabilityResponse(**response_data)

        max_date = today + timedelta(days=event_type.max_advance_days)
        if target_date > max_date:
            response_data["message"] = "วันที่เลือกอยู่นอกช่วงที่อนุญาตให้จองล่วงหน้า"
            return AvailabilityResponse(**response_data)

        if not template:
            response_data["message"] = "ยังไม่ได้ตั้งค่าเวลาทำการสำหรับบริการนี้"
            return AvailabilityResponse(**response_data)

        day_enum = convert_python_weekday(target_date.weekday())

        availabilities = db.query(models.Availability).filter(
            models.Availability.template_id == template.id,
            models.Availability.day_of_week == models.DayOfWeek(day_enum),
            models.Availability.is_active == True
        ).all()

        base_slots: List[str] = []
        for avail in availabilities:
            base_slots.extend(generate_time_slots(avail.start_time, avail.end_time, event_type.duration_minutes))

        date_override = get_relevant_date_override(db, template.id if template else None, target_date)

        if date_override:
            if date_override.is_unavailable:
                response_data["message"] = date_override.reason or "ไม่เปิดให้จองในวันนี้"
                response_data["slots"] = []
                return AvailabilityResponse(**response_data)
            elif date_override.custom_start_time and date_override.custom_end_time:
                base_slots = generate_time_slots(
                    date_override.custom_start_time,
                    date_override.custom_end_time,
                    event_type.duration_minutes
                )

        if not base_slots:
            # No slots configured for this day
            response_data["message"] = response_data["message"] or "ไม่มีเวลาว่างสำหรับวันนี้"
            return AvailabilityResponse(**response_data)

        resource_limits = resolve_resource_limits(template, target_date)
        base_capacity = resource_limits["rooms_limit"] or 1
        if resource_limits["max_concurrent"]:
            base_capacity = min(base_capacity, resource_limits["max_concurrent"])

        min_booking_time = datetime.now() + timedelta(hours=event_type.min_notice_hours)
        slot_duration = timedelta(minutes=event_type.duration_minutes)

        available_slots: List[TimeSlot] = []
        seen_slots = set()

        for slot in sorted(base_slots):
            if slot in seen_slots:
                continue
            seen_slots.add(slot)

            slot_start = parse_datetime(date, slot)
            slot_end = slot_start + slot_duration

            reason = None
            remaining_slots = 0
            capacity_limit = base_capacity
            available_provider_ids: Optional[List[int]] = None

            if is_slot_blocked_by_override(date_override, target_date, slot_start, slot_end):
                reason = "template_override"
                if template.requires_provider_assignment:
                    available_provider_ids = []
                capacity_limit = 0
            elif slot_start < min_booking_time:
                reason = "slot_too_soon"
            else:
                provider_pool_ids: Optional[List[int]] = None

                if template.requires_provider_assignment:
                    available_provider_ids = collect_available_providers(
                        db,
                        template,
                        target_date,
                        slot_start,
                        slot_end,
                        date_override
                    )
                    if provider_id:
                        if provider_id not in available_provider_ids:
                            reason = "provider_unavailable"
                            available_provider_ids = []
                        else:
                            available_provider_ids = [provider_id]
                    if not reason and available_provider_ids:
                        capacity_limit = min(capacity_limit, len(available_provider_ids))
                    elif not reason:
                        reason = "no_provider"
                        available_provider_ids = []
                else:
                    provider_pool_ids = collect_available_providers(
                        db,
                        template,
                        target_date,
                        slot_start,
                        slot_end,
                        date_override
                    )
                    if provider_pool_ids:
                        capacity_limit = min(capacity_limit, len(provider_pool_ids))
                    elif not reason:
                        reason = "no_provider"

                if reason not in {"no_provider", "provider_unavailable"}:
                    bookings = fetch_slot_bookings(
                        db,
                        event_type_id,
                        slot_start,
                        slot_end
                    )

                    if template.requires_provider_assignment:
                        booked_provider_ids = {appt.provider_id for appt in bookings if appt.provider_id}
                        unassigned_bookings = len([appt for appt in bookings if not appt.provider_id])

                        if available_provider_ids is None:
                            available_provider_ids = []

                        remaining_providers = [pid for pid in available_provider_ids if pid not in booked_provider_ids]
                        occupied_slots = len(booked_provider_ids) + unassigned_bookings
                        capacity_limit = max(capacity_limit, 0)
                        remaining_slots = max(capacity_limit - occupied_slots, 0)

                        # Keep all available providers for user selection
                        # Don't limit by remaining_slots - user should see all available providers
                        available_provider_ids = remaining_providers

                        # But check if slot is still available
                        if remaining_slots == 0:
                            reason = reason or "fully_booked"
                            available_provider_ids = []
                    else:
                        remaining_slots = max(capacity_limit - len(bookings), 0)
                        if remaining_slots == 0:
                            reason = "fully_booked"

            if reason in {"no_provider", "provider_unavailable", "template_override"}:
                capacity_limit = 0

            if template.requires_provider_assignment and available_provider_ids is None:
                available_provider_ids = []

            available_slots.append(TimeSlot(
                time=slot,
                available=reason is None and remaining_slots > 0,
                remaining_slots=remaining_slots if remaining_slots > 0 else 0,
                total_capacity=capacity_limit,
                available_provider_ids=available_provider_ids if template.requires_provider_assignment else None,
                unavailable_reason=reason
            ))
        
        if event_type.max_bookings_per_day:
            daily_bookings = db.query(models.Appointment).filter(
                models.Appointment.event_type_id == event_type_id,
                models.Appointment.status.in_(['confirmed', 'pending']),
                models.Appointment.start_time >= datetime.combine(target_date, time.min),
                models.Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min)
            ).count()

            if daily_bookings >= event_type.max_bookings_per_day:
                available_slots = []
                response_data["message"] = "เต็มตามจำนวนที่อนุญาตต่อวัน"

        response_data["slots"] = available_slots

        if provider_id:
            provider = db.query(models.Provider).filter_by(id=provider_id).first()
            if provider:
                response_data["provider"] = {
                    "id": provider.id,
                    "name": provider.name,
                    "title": provider.title
                }

        return AvailabilityResponse(**response_data)
        
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error getting availability: {str(e)}")

@router.post("/booking/create") 
async def create_booking(
    subdomain: str,
    booking: BookingCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)  # ใช้ get_db ปกติ
):
    """Create a new appointment booking"""
    
    schema_name = f"tenant_{subdomain}"
    # Set search_path ด้วยตัวเองในแต่ละ function
    schema_name = f"tenant_{subdomain}"
    try:
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        db.commit()  # ต้อง commit หลัง set search_path
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {subdomain}")
    
    try:
        # 1. Validate event type
        event_type = db.query(models.EventType).filter_by(
            id=booking.event_type_id,
            is_active=True
        ).first()
        
        if not event_type:
            raise HTTPException(404, "Event type not found or inactive")
        
        # 2. Parse and validate datetime
        appointment_datetime = parse_datetime(booking.date, booking.time)
        
        # Check not in past
        if appointment_datetime < datetime.now():
            raise HTTPException(400, "Cannot book in the past")
        
        # Check minimum notice
        min_booking_time = datetime.now() + timedelta(hours=event_type.min_notice_hours)
        if appointment_datetime < min_booking_time:
            raise HTTPException(
                400, 
                f"Booking requires at least {event_type.min_notice_hours} hours notice"
            )
        
        template = event_type.availability_template
        if not template:
            raise HTTPException(400, "บริการนี้ยังไม่ได้ตั้งค่าเวลาทำการ")

        # Enforce daily booking limit before allocating provider
        if event_type.max_bookings_per_day:
            target_date = appointment_datetime.date()
            daily_bookings = db.query(models.Appointment).filter(
                models.Appointment.event_type_id == booking.event_type_id,
                models.Appointment.status.in_(['confirmed', 'pending']),
                models.Appointment.start_time >= datetime.combine(target_date, time.min),
                models.Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min)
            ).count()

            if daily_bookings >= event_type.max_bookings_per_day:
                raise HTTPException(409, "จำนวนการจองต่อวันเต็มแล้ว")

        slot_end = appointment_datetime + timedelta(minutes=event_type.duration_minutes)
        assigned_provider_id = ensure_slot_capacity(
            db,
            event_type,
            template,
            appointment_datetime,
            slot_end,
            booking.provider_id
        )

        provider_to_use = assigned_provider_id
        
        # 4. Create or find patient
        patient = None
        if booking.guest_email:
            patient = db.query(models.Patient).filter_by(
                email=booking.guest_email
            ).first()
        
        if not patient and booking.guest_phone:
            patient = db.query(models.Patient).filter_by(
                phone_number=booking.guest_phone
            ).first()
        
        if not patient:
            patient = models.Patient(
                name=booking.guest_name,
                email=booking.guest_email,
                phone_number=booking.guest_phone
            )
            db.add(patient)
            db.flush()
        
        # 5. Get or create service type (default)
        service_type = db.query(models.ServiceType).filter_by(
            name="General"
        ).first()
        
        if not service_type:
            service_type = models.ServiceType(
                name="General",
                description="General appointment",
                is_active=True
            )
            db.add(service_type)
            db.flush()
        
        # 6. Create appointment
        booking_ref = generate_booking_reference()
        
        appointment = models.Appointment(
            patient_id=patient.id,
            provider_id=provider_to_use,  # อาจเป็น None หาก template ไม่บังคับเลือกผู้ให้บริการ
            event_type_id=booking.event_type_id,
            service_type_id=service_type.id,
            start_time=appointment_datetime,
            end_time=slot_end,
            booking_reference=booking_ref,
            status='confirmed',
            guest_name=booking.guest_name,
            guest_email=booking.guest_email,
            guest_phone=booking.guest_phone,
            notes=booking.notes
        )
        
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        
        # 7. Queue email notification (mock for now)
        if booking.guest_email:
            background_tasks.add_task(
                send_confirmation_email,
                booking.guest_email,
                appointment,
                event_type
            )
        
        # 8. Return confirmation
        return BookingResponse(
            success=True,
            booking_reference=booking_ref,
            appointment_datetime=appointment_datetime.isoformat(),
            guest_name=booking.guest_name,
            event_type_name=event_type.name,
            provider_name=None,  # Will add when provider system is ready
            location=getattr(event_type, 'location', 'จะแจ้งให้ทราบ'),
            instructions=getattr(event_type, 'instructions', None),
            message="การจองสำเร็จ! รายละเอียดถูกส่งไปยัง email ของคุณแล้ว"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error creating booking: {str(e)}")

@router.get("/booking/{booking_reference}")
async def get_booking_details(
    subdomain: str,
    booking_reference: str,
    db: Session = Depends(get_db)   
):
    """Get booking details by reference"""
    
    # Set search_path ทุกครั้ง
    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()

    appointment = db.query(models.Appointment).filter_by(
        booking_reference=booking_reference
    ).first()
    
    if not appointment:
        raise HTTPException(404, "Booking not found")
    
    # Get related data
    event_type = db.query(models.EventType).filter_by(
        id=appointment.event_type_id
    ).first()
    
    provider = None
    if appointment.provider_id:
        provider = db.query(models.Provider).filter_by(
            id=appointment.provider_id
        ).first()
    
    return {
        "booking_reference": appointment.booking_reference,
        "status": appointment.status,
        "appointment_datetime": appointment.start_time.isoformat(),
        "end_time": appointment.end_time.isoformat(),
        "guest_name": appointment.guest_name,
        "guest_email": appointment.guest_email,
        "guest_phone": appointment.guest_phone,
        "notes": appointment.notes,
        "event_type": {
            "id": event_type.id if event_type else None,
            "name": event_type.name,
            "duration": event_type.duration_minutes
        } if event_type else None,
        "provider": {
            "name": f"{provider.title} {provider.name}" if provider.title else provider.name,
            "department": provider.department
        } if provider else None,
        "can_reschedule": appointment.start_time > datetime.now() + timedelta(hours=4),
        "can_cancel": appointment.start_time > datetime.now() + timedelta(hours=4),
        "created_at": appointment.created_at.isoformat()
    }

@router.post("/booking/reschedule")
async def reschedule_booking(
    subdomain: str,
    request: RescheduleRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)  
):
    """Reschedule an existing booking"""

    # Set search_path
    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
        # 1. Find original appointment
        original = db.query(models.Appointment).filter(
            models.Appointment.booking_reference == request.booking_reference,
            models.Appointment.status.in_(['confirmed', 'cancelled'])
        ).first()
        
        if not original:
            raise HTTPException(404, "Booking not found or already modified")
        
        # 2. Check if can reschedule
        if original.status == 'confirmed' and original.start_time <= datetime.now() + timedelta(hours=4):
            raise HTTPException(400, "Cannot reschedule within 4 hours of appointment")
        
        # 3. Parse new datetime
        new_datetime = parse_datetime(request.new_date, request.new_time)
        
        # 4. Get event type for duration
        event_type = db.query(models.EventType).filter_by(
            id=original.event_type_id
        ).first()
        
        if new_datetime < datetime.now():
            raise HTTPException(400, "ไม่สามารถเลื่อนนัดไปยังเวลาที่ผ่านมาแล้วได้")

        min_booking_time = datetime.now() + timedelta(hours=event_type.min_notice_hours)
        if new_datetime < min_booking_time:
            raise HTTPException(400, "ต้องแจ้งเลื่อนล่วงหน้าตามเวลาที่กำหนด")

        template = event_type.availability_template
        if not template:
            raise HTTPException(400, "บริการนี้ยังไม่ได้ตั้งค่าเวลาทำการ")

        if event_type.max_bookings_per_day:
            target_date = new_datetime.date()
            daily_bookings = db.query(models.Appointment).filter(
                models.Appointment.id != original.id,
                models.Appointment.event_type_id == original.event_type_id,
                models.Appointment.status.in_(['confirmed', 'pending']),
                models.Appointment.start_time >= datetime.combine(target_date, time.min),
                models.Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min)
            ).count()

            if daily_bookings >= event_type.max_bookings_per_day:
                raise HTTPException(409, "จำนวนการจองต่อวันเต็มแล้ว")

        new_end = new_datetime + timedelta(minutes=event_type.duration_minutes)

        requested_provider_id = request.provider_id or original.provider_id

        try:
            assigned_provider_id = ensure_slot_capacity(
                db,
                event_type,
                template,
                new_datetime,
                new_end,
                requested_provider_id
            )
        except HTTPException as exc:
            if template.requires_provider_assignment and exc.status_code == 409 and not request.provider_id:
                assigned_provider_id = ensure_slot_capacity(
                    db,
                    event_type,
                    template,
                    new_datetime,
                    new_end,
                    None
                )
            else:
                raise

        original.start_time = new_datetime
        original.end_time = new_end
        original.provider_id = assigned_provider_id
        original.status = 'confirmed'
        original.cancelled_at = None
        original.cancelled_by = None
        original.cancellation_reason = None
        original.reschedule_count = (original.reschedule_count or 0) + 1

        if request.reason:
            note_entry = f"[Reschedule] {request.reason}"
            if original.internal_notes:
                original.internal_notes = f"{original.internal_notes}\n{note_entry}"
            else:
                original.internal_notes = note_entry

        db.commit()

        if original.guest_email:
            background_tasks.add_task(
                send_reschedule_email,
                original.guest_email,
                original,
                event_type
            )

        return {
            "success": True,
            "booking_reference": original.booking_reference,
            "new_appointment_datetime": new_datetime.isoformat(),
            "provider_id": assigned_provider_id,
            "message": "เลื่อนนัดหมายเรียบร้อยแล้ว"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error rescheduling: {str(e)}")


@router.post("/booking/restore")
async def restore_booking(
    subdomain: str,
    request: RestoreRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Restore a previously cancelled booking if the original slot is still available."""

    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()

    try:
        appointment = db.query(models.Appointment).filter_by(
            booking_reference=request.booking_reference
        ).first()

        if not appointment:
            raise HTTPException(404, "ไม่พบนัดหมายที่ต้องการกู้คืน")

        if appointment.status != 'cancelled':
            raise HTTPException(400, "นัดหมายนี้ไม่ได้อยู่ในสถานะถูกยกเลิก")

        if appointment.start_time <= datetime.now():
            raise HTTPException(400, "ไม่สามารถกู้คืนนัดหมายที่เลยเวลาแล้วได้")

        event_type = db.query(models.EventType).filter_by(
            id=appointment.event_type_id
        ).first()

        if not event_type:
            raise HTTPException(400, "ไม่พบบริการของนัดหมายนี้")

        template = event_type.availability_template

        if not template:
            raise HTTPException(400, "บริการนี้ยังไม่ได้ตั้งค่าเวลาทำการ")

        slot_start = appointment.start_time
        slot_end = appointment.end_time

        try:
            assigned_provider_id = ensure_slot_capacity(
                db,
                event_type,
                template,
                slot_start,
                slot_end,
                appointment.provider_id
            )
        except HTTPException as exc:
            if exc.status_code == 409:
                raise HTTPException(409, "ไม่สามารถกู้คืนนัดหมายได้ เนื่องจากช่วงเวลานี้ถูกจองแล้ว กรุณาเลื่อนนัดไปเวลาอื่น")
            raise

        appointment.status = 'confirmed'
        appointment.cancelled_at = None
        appointment.cancelled_by = None
        appointment.cancellation_reason = None
        appointment.provider_id = assigned_provider_id
        appointment.reschedule_count = appointment.reschedule_count or 0

        if request.reason:
            note_entry = f"[Restore] {request.reason}"
            if appointment.internal_notes:
                appointment.internal_notes = f"{appointment.internal_notes}\n{note_entry}"
            else:
                appointment.internal_notes = note_entry

        db.commit()

        if appointment.guest_email:
            background_tasks.add_task(
                send_reschedule_email,
                appointment.guest_email,
                appointment,
                event_type
            )

        return {
            "success": True,
            "booking_reference": appointment.booking_reference,
            "message": "กู้คืนนัดหมายเรียบร้อยแล้ว"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error restoring booking: {str(e)}")

@router.post("/booking/cancel")
async def cancel_booking(
    subdomain: str,
    request: CancelRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)  
):
    """Cancel an existing booking"""
    # Set search_path
    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()

    try:
        # Find appointment
        appointment = db.query(models.Appointment).filter_by(
            booking_reference=request.booking_reference,
            status='confirmed'
        ).first()
        
        if not appointment:
            raise HTTPException(404, "Booking not found or already cancelled")
        
        # Check if can cancel
        if appointment.start_time <= datetime.now() + timedelta(hours=4):
            raise HTTPException(400, "Cannot cancel within 4 hours of appointment")
        
        # Update status
        appointment.status = 'cancelled'
        appointment.cancelled_at = datetime.now()
        appointment.cancelled_by = 'patient'
        appointment.cancellation_reason = request.reason
        
        db.commit()
        
        # Send notification
        if appointment.guest_email:
            background_tasks.add_task(
                send_cancellation_email,
                appointment.guest_email,
                appointment
            )
        
        return {
            "success": True,
            "booking_reference": request.booking_reference,
            "cancelled_at": appointment.cancelled_at.isoformat(),
            "message": "การยกเลิกนัดสำเร็จ"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error cancelling: {str(e)}")
    
@router.post("/booking/search")
async def search_appointments(
    subdomain: str,
    search: AppointmentSearch,
    db: Session = Depends(get_db)
):
    """Search appointments by email, phone, or reference"""
    
    # Set search_path
    schema_name = f"tenant_{subdomain}"
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    db.commit()
    
    try:
        # Build query based on search type
        query = db.query(models.Appointment)
        
        if search.search_type == 'email':
            # ✅ Case-insensitive email search
            from sqlalchemy import func
            query = query.filter(
                func.lower(models.Appointment.guest_email) == func.lower(search.search_value)
            )
        elif search.search_type == 'phone':
            # Clean phone number (remove spaces, dashes)
            clean_phone = search.search_value.replace(' ', '').replace('-', '')
            query = query.filter(
                models.Appointment.guest_phone == clean_phone
            )
        elif search.search_type == 'reference':
            query = query.filter(
                models.Appointment.booking_reference == search.search_value.upper()
            )
        else:
            raise HTTPException(400, "Invalid search type")
        
        # Only show confirmed appointments
        appointments = query.filter(
            models.Appointment.status.in_(['confirmed', 'pending'])
        ).order_by(
            models.Appointment.start_time.desc()
        ).limit(20).all()
        
        # Format results
        results = []
        for apt in appointments:
            # Get event type
            event_type = db.query(models.EventType).filter_by(
                id=apt.event_type_id
            ).first()
            
            # Get provider if exists
            provider = None
            if apt.provider_id:
                provider = db.query(models.Provider).filter_by(
                    id=apt.provider_id
                ).first()
            
            results.append({
                "booking_reference": apt.booking_reference,
                "appointment_datetime": apt.start_time.isoformat(),
                "end_time": apt.end_time.isoformat(),
                "guest_name": apt.guest_name,
                "guest_email": apt.guest_email,
                "guest_phone": apt.guest_phone,
                "status": apt.status,
                "notes": apt.notes,
                "event_type": {
                    "id": event_type.id,
                    "name": event_type.name,
                    "duration": event_type.duration_minutes
                } if event_type else None,
                "provider": {
                    "name": f"{provider.title} {provider.name}" if provider else None,
                    "department": provider.department if provider else None
                } if provider else None,
                "created_at": apt.created_at.isoformat()
            })
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error searching appointments: {str(e)}")

# --- Email Functions (Mock) ---
async def send_confirmation_email(email: str, appointment, event_type):
    """Send booking confirmation email"""
    print(f"📧 Sending confirmation to {email}")
    print(f"   Reference: {appointment.booking_reference}")
    print(f"   DateTime: {appointment.start_time}")
    print(f"   Event: {event_type.name}")
    # TODO: Integrate with real email service

async def send_reschedule_email(email: str, appointment, event_type):
    """Send reschedule confirmation email"""
    print(f"📧 Sending reschedule confirmation to {email}")
    print(f"   New Reference: {appointment.booking_reference}")
    print(f"   New DateTime: {appointment.start_time}")

async def send_cancellation_email(email: str, appointment):
    """Send cancellation confirmation email"""
    print(f"📧 Sending cancellation confirmation to {email}")
    print(f"   Reference: {appointment.booking_reference}")