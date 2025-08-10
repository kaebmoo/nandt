# hospital-booking/flask_app/app/models.py

from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey,
                        create_engine, event)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.schema import CreateSchema
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

Base = declarative_base()

# --- Public Schema Models ---
class Hospital(Base):
    __tablename__ = 'hospitals'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    subdomain = Column(String(50), unique=True, nullable=False, index=True)
    schema_name = Column(String(50), unique=True, nullable=False)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))
    users = relationship("User", back_populates="hospital", cascade="all, delete-orphan")

class User(Base):
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
class Patient(Base):
    __tablename__ = 'patients'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), unique=True, index=True)
    email = Column(String(120), unique=True, nullable=True, index=True)
    
class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    notes = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    patient = relationship("Patient")

# Event to create schema for a new hospital
# hospital-booking/flask_app/app/models.py

from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey,
                        create_engine, event)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.schema import CreateSchema
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

# สร้าง Base แยกสำหรับ public schema และ tenant schemas
PublicBase = declarative_base()
TenantBase = declarative_base()

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

# --- Tenant Specific Models (ไม่ควรสร้างใน public schema) ---
class Patient(TenantBase):
    __tablename__ = 'patients'
    # ไม่กำหนด schema เพราะจะถูกสร้างใน tenant schema แต่ละอัน
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), unique=True, index=True)
    email = Column(String(120), unique=True, nullable=True, index=True)
    
class Appointment(TenantBase):
    __tablename__ = 'appointments'
    # ไม่กำหนด schema เพราะจะถูกสร้างใน tenant schema แต่ละอัน
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    notes = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    patient = relationship("Patient")

# สำหรับ backward compatibility - export Base เป็น PublicBase
Base = PublicBase

# Event to create schema for a new hospital
@event.listens_for(Hospital, 'after_insert')
def receive_after_insert(mapper, connection, target):
    """
    สร้าง schema และ tables สำหรับโรงพยาบาลใหม่
    """
    schema_name = target.schema_name
    
    # 1. สร้าง schema
    connection.execute(CreateSchema(schema_name, if_not_exists=True))
    
    # 2. สร้าง tenant tables ใน schema ใหม่
    tenant_tables = [Patient.__table__, Appointment.__table__]
    
    # เก็บ schema เดิมไว้
    original_schema = TenantBase.metadata.schema
    
    try:
        # ตั้งค่า schema ใหม่สำหรับ TenantBase
        TenantBase.metadata.schema = schema_name
        
        # สร้าง tables ทุกตัวใน schema ใหม่
        for table in tenant_tables:
            # สร้างสำเนาของ table โดยเปลี่ยน schema
            table_copy = table.tometadata(TenantBase.metadata, schema=schema_name)
            table_copy.create(connection, checkfirst=True)
            
        print(f"✅ Created schema '{schema_name}' with tables: {[t.name for t in tenant_tables]}")
            
    except Exception as e:
        print(f"❌ Error creating schema '{schema_name}': {e}")
        raise
    finally:
        # คืนค่า schema เดิม
        TenantBase.metadata.schema = original_schema