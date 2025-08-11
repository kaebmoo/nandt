# hospital-booking/flask_app/app/models.py - แก้ไข Bug

from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey,
                        create_engine, event, Boolean, 
                        Time, Text, Enum as SQLEnum, JSON)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.schema import CreateSchema
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import enum
import random
import string

# สร้าง Base แยกสำหรับ public schema และ tenant schemas
PublicBase = declarative_base()
TenantBase = declarative_base()

# --- Enum Definitions (ต้องประกาศก่อน Models) ---
class DayOfWeek(enum.Enum):
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6

# --- Public Schema Models (เฉพาะ tables ที่ต้องอยู่ใน public) ---
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
class Patient(TenantBase):
    __tablename__ = 'patients'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), index=True)
    email = Column(String(120), index=True)
    
    # Additional details
    date_of_birth = Column(DateTime)
    national_id = Column(String(20))  # เลขบัตรประชาชน
    address = Column(Text)
    emergency_contact = Column(String(100))
    emergency_phone = Column(String(20))
    
    # Medical info
    allergies = Column(Text)
    medical_conditions = Column(Text)
    current_medications = Column(Text)
    
    # Preferences
    preferred_language = Column(String(10), default='th')
    communication_preference = Column(String(20), default='sms')  # sms, email, phone
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class EventType(TenantBase):
    """ประเภทการนัดหมาย เช่น ฉีดวัคซีน, Health Screening"""
    __tablename__ = 'event_types'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # "ฉีดวัคซีน"
    slug = Column(String(50), nullable=False, unique=True)  # "vaccination"
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False, default=30)
    color = Column(String(7), default="#6366f1")  # hex color
    is_active = Column(Boolean, default=True)
    
    # เลือกรูปแบบเวลาจาก availability
    availability_id = Column(Integer, ForeignKey('availabilities.id'), nullable=True)
    
    # Buffer times
    buffer_before_minutes = Column(Integer, default=0)
    buffer_after_minutes = Column(Integer, default=0)
    
    # Advanced settings
    max_bookings_per_day = Column(Integer)  # จำกัดจำนวนการจองต่อวัน
    min_notice_hours = Column(Integer, default=4)  # ต้องจองล่วงหน้าอย่างน้อย
    max_advance_days = Column(Integer, default=60)  # จองได้ล่วงหน้าสูงสุด
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    availability = relationship("Availability", back_populates="event_types")
    appointments = relationship("Appointment", back_populates="event_type")

class ServiceType(TenantBase):
    """ประเภทบริการ เช่น General Health, Vaccination, Health Screening"""
    __tablename__ = 'service_types'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    appointments = relationship("Appointment", back_populates="service_type")

class Provider(TenantBase):
    """ผู้ให้บริการ - หมอ/เจ้าหน้าที่"""
    __tablename__ = 'providers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    title = Column(String(50))  # "นพ.", "พญ."
    department = Column(String(100))
    email = Column(String(120))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    
    # Public booking settings
    public_booking_url = Column(String(100), unique=True)  # "dr-somchai"
    bio = Column(Text)
    profile_image_url = Column(String(255))
    
    # Relationships  
    appointments = relationship("Appointment", back_populates="provider")

class Availability(TenantBase):
    """ตารางรูปแบบเวลาทำงาน (Schedule Template)"""
    __tablename__ = 'availabilities'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # "จันทร์-ศุกร์ (08:30-16:30)"
    description = Column(Text)  # คำอธิบายรูปแบบเวลา
    
    # Weekly recurring schedule
    day_of_week = Column(SQLEnum(DayOfWeek), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    # Timezone
    timezone = Column(String(50), default="Asia/Bangkok")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships - event types ที่ใช้ availability นี้
    event_types = relationship("EventType", back_populates="availability")
    date_overrides = relationship("DateOverride", 
                                 back_populates="template", 
                                 foreign_keys="DateOverride.template_id",
                                 cascade="all, delete-orphan")

class DateOverride(TenantBase):
    """การปรับเปลี่ยนตารางในวันเฉพาะ (วันหยุดพิเศษ, เปลี่ยนเวลาทำการ)"""
    __tablename__ = 'date_overrides'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)  # วันที่เฉพาะ
    
    # Template relationship
    template_id = Column(Integer, ForeignKey('availabilities.id'), nullable=True)
    template_scope = Column(String(50), default='template')  # 'template' or 'global'
    
    # Override types
    is_unavailable = Column(Boolean, default=False)  # วันหยุด
    custom_start_time = Column(Time)  # เวลาเริ่มต้นพิเศษ
    custom_end_time = Column(Time)    # เวลาสิ้นสุดพิเศษ
    
    reason = Column(String(255))  # เหตุผล เช่น "วันหยุดนักขัตฤกษ์"
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    template = relationship("Availability", back_populates="date_overrides", foreign_keys=[template_id])

class Holiday(TenantBase):
    """วันหยุดนักขัตฤกษ์"""
    __tablename__ = 'holidays'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    date = Column(DateTime, nullable=False)
    is_recurring = Column(Boolean, default=False)  # วันหยุดประจำปี
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
    
    # Booking details
    booking_reference = Column(String(20), unique=True)  # REF-ABC123
    status = Column(String(20), default='confirmed')  # confirmed, cancelled, rescheduled, completed
    
    # Contact info (ถ้าไม่มี patient record)
    guest_name = Column(String(100))
    guest_email = Column(String(120))
    guest_phone = Column(String(20))
    
    notes = Column(String(500))
    internal_notes = Column(Text)  # หมายเหตุภายใน
    
    # Notification settings
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime)
    
    # Cancellation/Reschedule
    cancelled_at = Column(DateTime)
    cancelled_by = Column(String(50))  # 'patient', 'provider', 'admin'
    cancellation_reason = Column(Text)
    
    rescheduled_from_id = Column(Integer, ForeignKey('appointments.id'))
    reschedule_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient")
    provider = relationship("Provider", back_populates="appointments")
    event_type = relationship("EventType", back_populates="appointments")
    service_type = relationship("ServiceType", back_populates="appointments")
    
    # Self-referential for rescheduling
    rescheduled_from = relationship("Appointment", remote_side=[id])

# สำหรับ backward compatibility - export Base เป็น PublicBase
Base = PublicBase

# Utility function สำหรับสร้าง booking reference
def generate_booking_reference():
    """สร้างรหัสอ้างอิง เช่น BK-A1B2C3"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"BK-{letters[0]}{numbers[0]}{letters[1]}{numbers[1]}{letters[2]}{numbers[2]}"

# Event to create schema for a new hospital
@event.listens_for(Hospital, 'after_insert')
def receive_after_insert(mapper, connection, target):
    """
    สร้าง schema และ tables สำหรับโรงพยาบาลใหม่
    """
    schema_name = target.schema_name
    
    # 1. สร้าง schema
    connection.execute(CreateSchema(schema_name, if_not_exists=True))
    
    # 2. สร้าง tenant tables ใน schema ใหม่ (ลำดับสำคัญ!)
    # ต้องสร้างตาม dependency order
    tenant_tables_order = [
        Patient.__table__,
        EventType.__table__,
        ServiceType.__table__, 
        Provider.__table__,
        Availability.__table__,
        DateOverride.__table__,
        Holiday.__table__,
        Appointment.__table__  # สุดท้าย เพราะมี FK หลายตัว
    ]
    
    # เก็บ schema เดิมไว้
    original_schema = TenantBase.metadata.schema
    
    try:
        # ตั้งค่า schema ใหม่สำหรับ TenantBase
        TenantBase.metadata.schema = schema_name
        
        # สร้าง tables ทีละตัวตามลำดับ
        for table in tenant_tables_order:
            # สร้างสำเนาของ table โดยเปลี่ยน schema
            table_copy = table.tometadata(TenantBase.metadata, schema=schema_name)
            table_copy.create(connection, checkfirst=True)
            
        print(f"✅ Created schema '{schema_name}' with {len(tenant_tables_order)} tables")
            
    except Exception as e:
        print(f"❌ Error creating schema '{schema_name}': {e}")
        raise
    finally:
        # คืนค่า schema เดิม
        TenantBase.metadata.schema = original_schema