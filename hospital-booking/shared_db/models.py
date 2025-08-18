# hospital-booking/flask_app/app/models.py - Updated with new structure

from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey,
                        create_engine, event, Boolean, 
                        Time, Text, Enum as SQLEnum, JSON, Date)
# from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.schema import CreateSchema
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import enum
import random
import string
from .database import PublicBase, TenantBase

# สร้าง Base แยกสำหรับ public schema และ tenant schemas
# PublicBase = declarative_base()
# TenantBase = declarative_base()

# --- Enum Definitions ---
class DayOfWeek(enum.Enum):
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6

# --- Public Schema Models ---
class Hospital(PublicBase):
    __tablename__ = 'hospitals'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    subdomain = Column(String(50), unique=True, nullable=False, index=True)
    schema_name = Column(String(50), unique=True, nullable=False)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))
    users = relationship("User", back_populates="hospital", cascade="all, delete-orphan")

class User(PublicBase):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(200))
    name = Column(String(100))
    phone_number = Column(String(20))
    hospital_id = Column(Integer, ForeignKey('public.hospitals.id'), nullable=False)
    hospital = relationship("Hospital", back_populates="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- Tenant Specific Models ---

class AvailabilityTemplate(TenantBase):
    """Template สำหรับตารางเวลาทำการ (ตารางใหม่!)"""
    __tablename__ = 'availability_templates'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)  # "จันทร์-ศุกร์ (08:30-16:30)"
    description = Column(Text)
    timezone = Column(String(50), default='Asia/Bangkok')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    availabilities = relationship("Availability", back_populates="template", cascade="all, delete-orphan")
    date_overrides = relationship("DateOverride", back_populates="template", cascade="all, delete-orphan")
    event_types = relationship("EventType", back_populates="availability_template")

class Availability(TenantBase):
    """ตารางเวลาทำการ (ปรับให้อ้างอิง template_id)"""
    __tablename__ = 'availabilities'
    
    id = Column(Integer, primary_key=True)
    
    # Reference to template (ใหม่!)
    template_id = Column(Integer, ForeignKey('availability_templates.id'), nullable=True)
    
    # ยังเก็บ fields เดิมไว้สำหรับ transition period
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    
    # ลบ event_type_id ออก (ถ้ามี)
    # event_type_id = Column(Integer, ForeignKey('event_types.id'), nullable=True)
    
    # Schedule details
    day_of_week = Column(SQLEnum(DayOfWeek), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    template = relationship("AvailabilityTemplate", back_populates="availabilities")
    provider = relationship("Provider")
    
    # ยังเก็บไว้สำหรับ backward compatibility
    # ลบ relationship นี้ออก
    # event_types_legacy = relationship("EventType", 
    #                                  foreign_keys="EventType.availability_id",
    #
    # เนื่องจากคุณ migration database เสร็จแล้ว และลบ column availability_id ไปแล้ว ต้องลบออกจาก models ด้วยครับ                                  back_populates="availability_legacy")

class EventType(TenantBase):
    """ประเภทการนัดหมาย (ปรับให้ใช้ template_id)"""
    __tablename__ = 'event_types'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False, default=30)
    color = Column(String(7), default="#6366f1")
    is_active = Column(Boolean, default=True)
    
    # ใช้ template_id แทน availability_id (ใหม่!)
    template_id = Column(Integer, ForeignKey('availability_templates.id', ondelete='SET NULL'), nullable=True)
    
    # เก็บ availability_id ไว้สำหรับ transition period
    # ไม่ได้ใช้แล้ว
    # availability_id = Column(Integer, ForeignKey('availabilities.id'), nullable=True)
    
    # Buffer times
    buffer_before_minutes = Column(Integer, default=0)
    buffer_after_minutes = Column(Integer, default=0)
    
    # Advanced settings
    max_bookings_per_day = Column(Integer)
    min_notice_hours = Column(Integer, default=4)
    max_advance_days = Column(Integer, default=60)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    availability_template = relationship("AvailabilityTemplate", back_populates="event_types")
    # ไม่ได้ใช้แล้ว
    # availability_legacy = relationship("Availability", 
    #                                   foreign_keys=[availability_id],
    #                                   back_populates="event_types_legacy")
    appointments = relationship("Appointment", back_populates="event_type")

class DateOverride(TenantBase):
    """การปรับเปลี่ยนตารางในวันเฉพาะ (ปรับให้อ้างอิง template)"""
    __tablename__ = 'date_overrides'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)  # เปลี่ยนเป็น Date แทน DateTime
    
    # Template relationship (อ้างอิง availability_templates)
    template_id = Column(Integer, ForeignKey('availability_templates.id', ondelete='CASCADE'), nullable=True)
    template_scope = Column(String(50), default='template')
    
    # Override types
    is_unavailable = Column(Boolean, default=False)
    custom_start_time = Column(Time)
    custom_end_time = Column(Time)
    
    reason = Column(String(255))
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    template = relationship("AvailabilityTemplate", back_populates="date_overrides")

class Patient(TenantBase):
    __tablename__ = 'patients'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), index=True)
    email = Column(String(120), index=True)
    
    # Additional details
    date_of_birth = Column(DateTime)
    national_id = Column(String(20))
    address = Column(Text)
    emergency_contact = Column(String(100))
    emergency_phone = Column(String(20))
    
    # Medical info
    allergies = Column(Text)
    medical_conditions = Column(Text)
    current_medications = Column(Text)
    
    # Preferences
    preferred_language = Column(String(10), default='th')
    communication_preference = Column(String(20), default='sms')
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ServiceType(TenantBase):
    __tablename__ = 'service_types'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    
    appointments = relationship("Appointment", back_populates="service_type")

class Provider(TenantBase):
    __tablename__ = 'providers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    title = Column(String(50))
    department = Column(String(100))
    email = Column(String(120))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    
    public_booking_url = Column(String(100), unique=True)
    bio = Column(Text)
    profile_image_url = Column(String(255))
    
    appointments = relationship("Appointment", back_populates="provider")
    availabilities = relationship("Availability", back_populates="provider")

class Holiday(TenantBase):
    __tablename__ = 'holidays'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    date = Column(DateTime, nullable=False)
    is_recurring = Column(Boolean, default=False)
    description = Column(Text)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Appointment(TenantBase):
    __tablename__ = 'appointments'
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    provider_id = Column(Integer, ForeignKey('providers.id'))
    event_type_id = Column(Integer, ForeignKey('event_types.id'))
    service_type_id = Column(Integer, ForeignKey('service_types.id'))
    
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    booking_reference = Column(String(20), unique=True)
    status = Column(String(20), default='confirmed')
    
    guest_name = Column(String(100))
    guest_email = Column(String(120))
    guest_phone = Column(String(20))
    
    notes = Column(String(500))
    internal_notes = Column(Text)
    
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime)
    
    cancelled_at = Column(DateTime)
    cancelled_by = Column(String(50))
    cancellation_reason = Column(Text)
    
    rescheduled_from_id = Column(Integer, ForeignKey('appointments.id'))
    reschedule_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    patient = relationship("Patient")
    provider = relationship("Provider", back_populates="appointments")
    event_type = relationship("EventType", back_populates="appointments")
    service_type = relationship("ServiceType", back_populates="appointments")
    rescheduled_from = relationship("Appointment", remote_side=[id])

# สำหรับ backward compatibility
Base = PublicBase

# Utility function
def generate_booking_reference():
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"VN-{letters[0]}{numbers[0]}{letters[1]}{numbers[1]}{letters[2]}{numbers[2]}"

# Event to create schema for a new hospital
@event.listens_for(Hospital, 'after_insert')
def receive_after_insert(mapper, connection, target):
    schema_name = target.schema_name
    
    connection.execute(CreateSchema(schema_name, if_not_exists=True))
    
    # ต้องสร้างตามลำดับ dependency
    tenant_tables_order = [
        Patient.__table__,
        ServiceType.__table__, 
        Provider.__table__,
        AvailabilityTemplate.__table__,  # ใหม่! ต้องสร้างก่อน Availability
        Availability.__table__,
        EventType.__table__,
        DateOverride.__table__,
        Holiday.__table__,
        Appointment.__table__
    ]
    
    original_schema = TenantBase.metadata.schema
    
    try:
        TenantBase.metadata.schema = schema_name
        
        for table in tenant_tables_order:
            table_copy = table.tometadata(TenantBase.metadata, schema=schema_name)
            table_copy.create(connection, checkfirst=True)
            
        print(f"✅ Created schema '{schema_name}' with {len(tenant_tables_order)} tables")
            
    except Exception as e:
        print(f"❌ Error creating schema '{schema_name}': {e}")
        raise
    finally:
        TenantBase.metadata.schema = original_schema