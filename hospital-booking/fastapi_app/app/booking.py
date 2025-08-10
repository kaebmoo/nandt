# fastapi_app/app/booking.py - Booking Management API

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import string
import random

# Import models
import sys
sys.path.append('flask_app/app')
import models

from .database import SessionLocal

router = APIRouter(prefix="/api/v1", tags=["booking"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Models
class BookingRequest(BaseModel):
    provider_id: int
    event_type_id: int
    date: str  # "2025-08-11"
    time: str  # "09:15"
    guest_name: str
    guest_email: EmailStr
    guest_phone: Optional[str] = None
    notes: Optional[str] = None
    service_type: str = "general"

class BookingResponse(BaseModel):
    success: bool
    message: str
    booking_reference: str
    booking_id: int
    appointment_datetime: str

class RescheduleRequest(BaseModel):
    booking_reference: str
    new_date: str
    new_time: str
    reason: Optional[str] = None

class CancelRequest(BaseModel):
    booking_reference: str
    reason: Optional[str] = None

# Helper Functions
def get_tenant_db(db: Session, subdomain: str):
    """Switch to tenant schema"""
    schema_name = f"tenant_{subdomain}"
    db.execute(f'SET search_path TO "{schema_name}", public')
    return db

def generate_booking_reference():
    """Generate booking reference like BK-A1B2C3"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"BK-{letters[0]}{numbers[0]}{letters[1]}{numbers[1]}{letters[2]}{numbers[2]}"

def validate_booking_slot(db: Session, provider_id: int, event_type_id: int, 
                         appointment_datetime: datetime) -> bool:
    """Validate if the time slot is available"""
    
    # Get event type for duration
    event_type = db.query(models.EventType).filter_by(id=event_type_id).first()
    if not event_type:
        return False
    
    end_datetime = appointment_datetime + timedelta(minutes=event_type.duration_minutes)
    
    # Check for conflicts
    conflicts = db.query(models.Appointment).filter(
        models.Appointment.provider_id == provider_id,
        models.Appointment.status.in_(['confirmed', 'rescheduled']),
        models.Appointment.start_time < end_datetime,
        models.Appointment.end_time > appointment_datetime
    ).first()
    
    return conflicts is None

def send_booking_confirmation(email: str, booking_data: dict):
    """Send booking confirmation email (mock implementation)"""
    print(f"📧 Sending confirmation email to {email}")
    print(f"Booking Reference: {booking_data['reference']}")
    print(f"Date: {booking_data['date']}")
    print(f"Time: {booking_data['time']}")
    # In real implementation, integrate with email service

def send_booking_reminder(email: str, booking_data: dict):
    """Send booking reminder (mock implementation)"""
    print(f"📱 Sending reminder to {email} for booking {booking_data['reference']}")

# API Endpoints

@router.post("/tenants/{subdomain}/book-appointment")
async def book_appointment(
    subdomain: str,
    booking: BookingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new appointment booking"""
    try:
        get_tenant_db(db, subdomain)
        
        # Parse date and time
        appointment_date = datetime.strptime(booking.date, "%Y-%m-%d").date()
        appointment_time = datetime.strptime(booking.time, "%H:%M").time()
        appointment_datetime = datetime.combine(appointment_date, appointment_time)
        
        # Validate minimum notice
        event_type = db.query(models.EventType).filter_by(id=booking.event_type_id).first()
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        min_notice = timedelta(hours=event_type.min_notice_hours)
        if appointment_datetime - datetime.now() < min_notice:
            raise HTTPException(
                status_code=400, 
                detail=f"Booking requires at least {event_type.min_notice_hours} hours notice"
            )
        
        # Validate slot availability
        if not validate_booking_slot(db, booking.provider_id, booking.event_type_id, appointment_datetime):
            raise HTTPException(status_code=409, detail="Time slot is not available")
        
        # Check or create patient record
        patient = None
        if booking.guest_email:
            patient = db.query(models.Patient).filter_by(email=booking.guest_email).first()
        
        if not patient and booking.guest_phone:
            patient = db.query(models.Patient).filter_by(phone_number=booking.guest_phone).first()
        
        if not patient:
            # Create new patient record
            patient = models.Patient(
                name=booking.guest_name,
                email=booking.guest_email,
                phone_number=booking.guest_phone
            )
            db.add(patient)
            db.flush()
        
        # Get or create service type
        service_type = db.query(models.ServiceType).filter_by(name=booking.service_type).first()
        if not service_type:
            service_type = models.ServiceType(name=booking.service_type, is_active=True)
            db.add(service_type)
            db.flush()
        
        # Calculate end time
        end_datetime = appointment_datetime + timedelta(minutes=event_type.duration_minutes)
        
        # Create appointment
        booking_ref = generate_booking_reference()
        appointment = models.Appointment(
            patient_id=patient.id,
            provider_id=booking.provider_id,
            event_type_id=booking.event_type_id,
            service_type_id=service_type.id,
            start_time=appointment_datetime,
            end_time=end_datetime,
            booking_reference=booking_ref,
            guest_name=booking.guest_name,
            guest_email=booking.guest_email,
            guest_phone=booking.guest_phone,
            notes=booking.notes,
            status='confirmed'
        )
        
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        
        # Send confirmation email in background
        booking_data = {
            'reference': booking_ref,
            'date': booking.date,
            'time': booking.time,
            'provider': 'นพ.สมชาย ใจดี',
            'event_type': event_type.name
        }
        background_tasks.add_task(send_booking_confirmation, booking.guest_email, booking_data)
        
        return BookingResponse(
            success=True,
            message="Booking confirmed successfully",
            booking_reference=booking_ref,
            booking_id=appointment.id,
            appointment_datetime=appointment_datetime.isoformat()
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/booking/{booking_reference}")
def get_booking_details(
    subdomain: str,
    booking_reference: str,
    db: Session = Depends(get_db)
):
    """Get booking details by reference"""
    try:
        get_tenant_db(db, subdomain)
        
        appointment = db.query(models.Appointment).filter_by(
            booking_reference=booking_reference
        ).first()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Get related data
        provider = db.query(models.Provider).filter_by(id=appointment.provider_id).first()
        event_type = db.query(models.EventType).filter_by(id=appointment.event_type_id).first()
        service_type = db.query(models.ServiceType).filter_by(id=appointment.service_type_id).first()
        
        return {
            "booking_reference": appointment.booking_reference,
            "status": appointment.status,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "guest_name": appointment.guest_name,
            "guest_email": appointment.guest_email,
            "guest_phone": appointment.guest_phone,
            "notes": appointment.notes,
            "provider": {
                "name": provider.name,
                "title": provider.title,
                "department": provider.department
            } if provider else None,
            "event_type": {
                "name": event_type.name,
                "duration_minutes": event_type.duration_minutes
            } if event_type else None,
            "service_type": service_type.name if service_type else None,
            "created_at": appointment.created_at.isoformat(),
            "can_reschedule": appointment.start_time > datetime.now() + timedelta(hours=4),
            "can_cancel": appointment.start_time > datetime.now() + timedelta(hours=4)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{subdomain}/reschedule-booking")
async def reschedule_booking(
    subdomain: str,
    reschedule: RescheduleRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Reschedule an existing booking"""
    try:
        get_tenant_db(db, subdomain)
        
        # Find original appointment
        original_appointment = db.query(models.Appointment).filter_by(
            booking_reference=reschedule.booking_reference,
            status='confirmed'
        ).first()
        
        if not original_appointment:
            raise HTTPException(status_code=404, detail="Booking not found or already modified")
        
        # Check if reschedule is allowed (4 hours before)
        if original_appointment.start_time <= datetime.now() + timedelta(hours=4):
            raise HTTPException(status_code=400, detail="Cannot reschedule within 4 hours of appointment")
        
        # Parse new date and time
        new_date = datetime.strptime(reschedule.new_date, "%Y-%m-%d").date()
        new_time = datetime.strptime(reschedule.new_time, "%H:%M").time()
        new_datetime = datetime.combine(new_date, new_time)
        
        # Validate new slot availability
        if not validate_booking_slot(db, original_appointment.provider_id, 
                                   original_appointment.event_type_id, new_datetime):
            raise HTTPException(status_code=409, detail="New time slot is not available")
        
        # Get event type for duration
        event_type = db.query(models.EventType).filter_by(
            id=original_appointment.event_type_id
        ).first()
        new_end_datetime = new_datetime + timedelta(minutes=event_type.duration_minutes)
        
        # Update original appointment status
        original_appointment.status = 'rescheduled'
        original_appointment.updated_at = datetime.now()
        
        # Create new appointment
        new_booking_ref = generate_booking_reference()
        new_appointment = models.Appointment(
            patient_id=original_appointment.patient_id,
            provider_id=original_appointment.provider_id,
            event_type_id=original_appointment.event_type_id,
            service_type_id=original_appointment.service_type_id,
            start_time=new_datetime,
            end_time=new_end_datetime,
            booking_reference=new_booking_ref,
            guest_name=original_appointment.guest_name,
            guest_email=original_appointment.guest_email,
            guest_phone=original_appointment.guest_phone,
            notes=original_appointment.notes,
            status='confirmed',
            rescheduled_from_id=original_appointment.id,
            reschedule_count=original_appointment.reschedule_count + 1
        )
        
        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)
        
        # Send confirmation email
        booking_data = {
            'reference': new_booking_ref,
            'date': reschedule.new_date,
            'time': reschedule.new_time,
            'provider': 'นพ.สมชาย ใจดี',
            'event_type': event_type.name,
            'old_reference': reschedule.booking_reference
        }
        background_tasks.add_task(send_booking_confirmation, 
                                original_appointment.guest_email, booking_data)
        
        return {
            "success": True,
            "message": "Booking rescheduled successfully",
            "new_booking_reference": new_booking_ref,
            "old_booking_reference": reschedule.booking_reference,
            "new_appointment_datetime": new_datetime.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{subdomain}/cancel-booking")
async def cancel_booking(
    subdomain: str,
    cancel: CancelRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Cancel an existing booking"""
    try:
        get_tenant_db(db, subdomain)
        
        # Find appointment
        appointment = db.query(models.Appointment).filter_by(
            booking_reference=cancel.booking_reference,
            status='confirmed'
        ).first()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Booking not found or already cancelled")
        
        # Check if cancellation is allowed (4 hours before)
        if appointment.start_time <= datetime.now() + timedelta(hours=4):
            raise HTTPException(status_code=400, detail="Cannot cancel within 4 hours of appointment")
        
        # Update appointment status
        appointment.status = 'cancelled'
        appointment.cancelled_at = datetime.now()
        appointment.cancelled_by = 'patient'
        appointment.cancellation_reason = cancel.reason
        appointment.updated_at = datetime.now()
        
        db.commit()
        
        # Send cancellation confirmation
        cancellation_data = {
            'reference': cancel.booking_reference,
            'reason': cancel.reason
        }
        # background_tasks.add_task(send_cancellation_confirmation, 
        #                         appointment.guest_email, cancellation_data)
        
        return {
            "success": True,
            "message": "Booking cancelled successfully",
            "booking_reference": cancel.booking_reference,
            "cancelled_at": appointment.cancelled_at.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/providers/{provider_id}/calendar")
def get_provider_calendar(
    subdomain: str,
    provider_id: int,
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db)
):
    """Get provider's calendar view"""
    try:
        get_tenant_db(db, subdomain)
        
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        # Get appointments in date range
        appointments = db.query(models.Appointment).filter(
            models.Appointment.provider_id == provider_id,
            models.Appointment.start_time >= datetime.combine(start, datetime.min.time()),
            models.Appointment.start_time <= datetime.combine(end, datetime.max.time()),
            models.Appointment.status.in_(['confirmed', 'rescheduled'])
        ).all()
        
        calendar_events = []
        for appointment in appointments:
            # Get related data
            patient = db.query(models.Patient).filter_by(id=appointment.patient_id).first()
            event_type = db.query(models.EventType).filter_by(id=appointment.event_type_id).first()
            
            calendar_events.append({
                "id": appointment.id,
                "booking_reference": appointment.booking_reference,
                "title": f"{appointment.guest_name or patient.name if patient else 'Unknown'} - {event_type.name if event_type else 'Appointment'}",
                "start": appointment.start_time.isoformat(),
                "end": appointment.end_time.isoformat(),
                "status": appointment.status,
                "patient_name": appointment.guest_name or (patient.name if patient else 'Unknown'),
                "contact": appointment.guest_phone or (patient.phone_number if patient else None),
                "notes": appointment.notes,
                "event_type": event_type.name if event_type else None,
                "can_edit": appointment.start_time > datetime.now() + timedelta(hours=1)
            })
        
        return {
            "events": calendar_events,
            "start_date": start_date,
            "end_date": end_date,
            "total_appointments": len(calendar_events)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/appointments/search")
def search_appointments(
    subdomain: str,
    query: str = "",
    status: str = "all",
    provider_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Search appointments with filters"""
    try:
        get_tenant_db(db, subdomain)
        
        # Build query
        appointments_query = db.query(models.Appointment)
        
        if provider_id:
            appointments_query = appointments_query.filter(
                models.Appointment.provider_id == provider_id
            )
        
        if status != "all":
            appointments_query = appointments_query.filter(
                models.Appointment.status == status
            )
        
        if date_from:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            appointments_query = appointments_query.filter(
                models.Appointment.start_time >= start_date
            )
        
        if date_to:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            appointments_query = appointments_query.filter(
                models.Appointment.start_time < end_date
            )
        
        if query:
            # Search in guest name, email, phone, or booking reference
            search_filter = (
                models.Appointment.guest_name.ilike(f"%{query}%") |
                models.Appointment.guest_email.ilike(f"%{query}%") |
                models.Appointment.guest_phone.ilike(f"%{query}%") |
                models.Appointment.booking_reference.ilike(f"%{query}%")
            )
            appointments_query = appointments_query.filter(search_filter)
        
        appointments = appointments_query.order_by(
            models.Appointment.start_time.desc()
        ).limit(limit).all()
        
        # Format results
        results = []
        for appointment in appointments:
            provider = db.query(models.Provider).filter_by(id=appointment.provider_id).first()
            event_type = db.query(models.EventType).filter_by(id=appointment.event_type_id).first()
            
            results.append({
                "id": appointment.id,
                "booking_reference": appointment.booking_reference,
                "guest_name": appointment.guest_name,
                "guest_email": appointment.guest_email,
                "guest_phone": appointment.guest_phone,
                "start_time": appointment.start_time.isoformat(),
                "end_time": appointment.end_time.isoformat(),
                "status": appointment.status,
                "provider_name": f"{provider.title} {provider.name}" if provider else "Unknown",
                "event_type": event_type.name if event_type else "Unknown",
                "notes": appointment.notes,
                "created_at": appointment.created_at.isoformat()
            })
        
        return {
            "appointments": results,
            "total": len(results),
            "query": query,
            "filters": {
                "status": status,
                "provider_id": provider_id,
                "date_from": date_from,
                "date_to": date_to
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{subdomain}/dashboard/stats")
def get_dashboard_stats(
    subdomain: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get dashboard statistics"""
    try:
        get_tenant_db(db, subdomain)
        
        # Default to current month if no dates provided
        if not date_from:
            today = datetime.now()
            date_from = today.replace(day=1).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        start_date = datetime.strptime(date_from, "%Y-%m-%d")
        end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        
        # Total appointments
        total_appointments = db.query(models.Appointment).filter(
            models.Appointment.start_time >= start_date,
            models.Appointment.start_time < end_date
        ).count()
        
        # Confirmed appointments
        confirmed_appointments = db.query(models.Appointment).filter(
            models.Appointment.start_time >= start_date,
            models.Appointment.start_time < end_date,
            models.Appointment.status == 'confirmed'
        ).count()
        
        # Cancelled appointments
        cancelled_appointments = db.query(models.Appointment).filter(
            models.Appointment.start_time >= start_date,
            models.Appointment.start_time < end_date,
            models.Appointment.status == 'cancelled'
        ).count()
        
        # Today's appointments
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        today_appointments = db.query(models.Appointment).filter(
            models.Appointment.start_time >= today_start,
            models.Appointment.start_time < today_end,
            models.Appointment.status == 'confirmed'
        ).count()
        
        # Unique patients
        unique_patients = db.query(models.Appointment.patient_id).filter(
            models.Appointment.start_time >= start_date,
            models.Appointment.start_time < end_date,
            models.Appointment.patient_id.isnot(None)
        ).distinct().count()
        
        # Most popular event types
        from sqlalchemy import func
        popular_event_types = db.query(
            models.EventType.name,
            func.count(models.Appointment.id).label('count')
        ).join(
            models.Appointment, models.EventType.id == models.Appointment.event_type_id
        ).filter(
            models.Appointment.start_time >= start_date,
            models.Appointment.start_time < end_date
        ).group_by(models.EventType.name).order_by(func.count(models.Appointment.id).desc()).limit(5).all()
        
        return {
            "period": {
                "from": date_from,
                "to": date_to
            },
            "totals": {
                "total_appointments": total_appointments,
                "confirmed_appointments": confirmed_appointments,
                "cancelled_appointments": cancelled_appointments,
                "today_appointments": today_appointments,
                "unique_patients": unique_patients,
                "cancellation_rate": round((cancelled_appointments / total_appointments * 100) if total_appointments > 0 else 0, 1)
            },
            "popular_event_types": [
                {"name": et[0], "count": et[1]} for et in popular_event_types
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))