# fastapi_app/app/booking.py - Complete Booking API

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, List, Dict
from datetime import datetime, timedelta, date, time
import string
import random
import sys

# Import database and models
from shared_db.database import SessionLocal
from shared_db import models

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

class AvailabilityResponse(BaseModel):
    date: str
    slots: List[TimeSlot]
    event_type: Dict
    provider: Optional[Dict] = None

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
        
        # 2. Parse date
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday
        
        # Convert to our DayOfWeek enum (0=Sunday, 6=Saturday)
        day_enum = (day_of_week + 1) % 7
        
        # 3. Check if date is not in the past
        if target_date < datetime.now().date():
            return AvailabilityResponse(
                date=date,
                slots=[],
                event_type={"name": event_type.name, "duration": event_type.duration_minutes}
            )
        
        # 4. Check if within booking window
        max_date = datetime.now().date() + timedelta(days=event_type.max_advance_days)
        if target_date > max_date:
            return AvailabilityResponse(
                date=date,
                slots=[],
                event_type={"name": event_type.name, "duration": event_type.duration_minutes}
            )
        
        # 5. Get base availability from template
        base_slots = []
        if event_type.template_id:
            availabilities = db.query(models.Availability).filter(
                models.Availability.template_id == event_type.template_id,
                models.Availability.day_of_week == models.DayOfWeek(day_enum),
                models.Availability.is_active == True
            ).all()
            
            for avail in availabilities:
                slots = generate_time_slots(
                    avail.start_time,
                    avail.end_time,
                    event_type.duration_minutes
                )
                base_slots.extend(slots)
        
        # 6. Check date overrides
        date_override = db.query(models.DateOverride).filter(
            models.DateOverride.date == target_date,
            or_(
                models.DateOverride.template_id == event_type.template_id,
                models.DateOverride.template_scope == 'global'
            )
        ).first()
        
        if date_override:
            if date_override.is_unavailable:
                # วันหยุด - ไม่มี slots
                base_slots = []
            elif date_override.custom_start_time and date_override.custom_end_time:
                # เวลาพิเศษ - ใช้เวลาจาก override แทน
                base_slots = generate_time_slots(
                    date_override.custom_start_time,
                    date_override.custom_end_time,
                    event_type.duration_minutes
                )
        
        # 7. Check holidays
        holiday = db.query(models.Holiday).filter(
            models.Holiday.date == target_date
        ).first()
        
        if holiday:
            base_slots = []  # No slots on holidays
        
        # 8. Filter out booked slots
        available_slots = []
        for slot in base_slots:
            slot_datetime = parse_datetime(date, slot)
            
            # Check minimum notice
            min_booking_time = datetime.now() + timedelta(hours=event_type.min_notice_hours)
            if slot_datetime < min_booking_time:
                continue
            
            # Check existing appointments
            slot_end = slot_datetime + timedelta(minutes=event_type.duration_minutes)
            
            # Count existing bookings for this slot
            existing_bookings = db.query(models.Appointment).filter(
                models.Appointment.event_type_id == event_type_id,
                models.Appointment.status.in_(['confirmed', 'pending']),
                models.Appointment.start_time < slot_end,
                models.Appointment.end_time > slot_datetime
            )
            
            if provider_id:
                existing_bookings = existing_bookings.filter(
                    models.Appointment.provider_id == provider_id
                )
            
            booking_count = existing_bookings.count()
            
            # Check max bookings per slot (default 1)
            max_per_slot = getattr(event_type, 'booking_per_slot', 1)
            
            if booking_count < max_per_slot:
                available_slots.append(TimeSlot(
                    time=slot,
                    available=True,
                    remaining_slots=max_per_slot - booking_count
                ))
        
        # 9. Check daily limit
        if event_type.max_bookings_per_day:
            daily_bookings = db.query(models.Appointment).filter(
                models.Appointment.event_type_id == event_type_id,
                models.Appointment.status.in_(['confirmed', 'pending']),
                models.Appointment.start_time >= datetime.combine(target_date, time.min),
                models.Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time.min)
            ).count()
            
            if daily_bookings >= event_type.max_bookings_per_day:
                available_slots = []
        
        # 10. Prepare response
        response = AvailabilityResponse(
            date=date,
            slots=available_slots,
            event_type={
                "id": event_type.id,
                "name": event_type.name,
                "duration": event_type.duration_minutes,
                "buffer_before": event_type.buffer_before_minutes,
                "buffer_after": event_type.buffer_after_minutes
            }
        )
        
        if provider_id:
            provider = db.query(models.Provider).filter_by(id=provider_id).first()
            if provider:
                response.provider = {
                    "id": provider.id,
                    "name": provider.name,
                    "title": provider.title
                }
        
        return response
        
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
        
        # 3. Check slot availability
        slot_end = appointment_datetime + timedelta(minutes=event_type.duration_minutes)
        
        conflict = db.query(models.Appointment).filter(
            models.Appointment.event_type_id == booking.event_type_id,
            models.Appointment.status.in_(['confirmed', 'pending']),
            models.Appointment.start_time < slot_end,
            models.Appointment.end_time > appointment_datetime
        )
        
        if booking.provider_id:
            conflict = conflict.filter(
                models.Appointment.provider_id == booking.provider_id
            )
        
        if conflict.first():
            raise HTTPException(409, "Time slot is not available")
        
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
            provider_id=booking.provider_id,  # Can be NULL for queue system
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
        original = db.query(models.Appointment).filter_by(
            booking_reference=request.booking_reference,
            status='confirmed'
        ).first()
        
        if not original:
            raise HTTPException(404, "Booking not found or already modified")
        
        # 2. Check if can reschedule
        if original.start_time <= datetime.now() + timedelta(hours=4):
            raise HTTPException(400, "Cannot reschedule within 4 hours of appointment")
        
        # 3. Parse new datetime
        new_datetime = parse_datetime(request.new_date, request.new_time)
        
        # 4. Get event type for duration
        event_type = db.query(models.EventType).filter_by(
            id=original.event_type_id
        ).first()
        
        new_end = new_datetime + timedelta(minutes=event_type.duration_minutes)
        
        # 5. Check new slot availability
        conflict = db.query(models.Appointment).filter(
            models.Appointment.id != original.id,
            models.Appointment.event_type_id == original.event_type_id,
            models.Appointment.status.in_(['confirmed', 'pending']),
            models.Appointment.start_time < new_end,
            models.Appointment.end_time > new_datetime
        )
        
        if original.provider_id:
            conflict = conflict.filter(
                models.Appointment.provider_id == original.provider_id
            )
        
        if conflict.first():
            raise HTTPException(409, "New time slot is not available")
        
        # 6. Update appointment
        original.status = 'rescheduled'
        
        # 7. Create new appointment
        new_ref = generate_booking_reference()
        new_appointment = models.Appointment(
            patient_id=original.patient_id,
            provider_id=original.provider_id,
            event_type_id=original.event_type_id,
            service_type_id=original.service_type_id,
            start_time=new_datetime,
            end_time=new_end,
            booking_reference=new_ref,
            status='confirmed',
            guest_name=original.guest_name,
            guest_email=original.guest_email,
            guest_phone=original.guest_phone,
            notes=original.notes,
            rescheduled_from_id=original.id,
            reschedule_count=(original.reschedule_count or 0) + 1
        )
        
        db.add(new_appointment)
        db.commit()
        
        # 8. Send notification
        if original.guest_email:
            background_tasks.add_task(
                send_reschedule_email,
                original.guest_email,
                new_appointment,
                event_type
            )
        
        return {
            "success": True,
            "new_booking_reference": new_ref,
            "old_booking_reference": request.booking_reference,
            "new_appointment_datetime": new_datetime.isoformat(),
            "message": "การเลื่อนนัดสำเร็จ!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error rescheduling: {str(e)}")

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