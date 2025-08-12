# fastapi_app/app/main.py - Universal URL generation

import os
import stripe
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, Header, HTTPException, Body, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, constr
from typing import Literal
from dotenv import load_dotenv

load_dotenv()

# Import models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'flask_app', 'app'))
import models 

from .database import SessionLocal, engine

# Import routers
from .event_types import router as event_types_router
from .availability import router as availability_router
from .booking import router as booking_router

# สร้างเฉพาะ public tables
models.PublicBase.metadata.create_all(bind=engine)

# --- Configuration ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
PRICE_IDS = {
    'basic': 'price_1PgZqgP8aZg8A7z6o9y7x8z9',
    'professional': 'price_1PgZqgP8aZg8A7z6a1b2c3d4'
}

# Universal domain configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
DOMAIN = os.environ.get('DOMAIN', 'localhost')  # localhost หรือ yourdomain.com
USE_HTTPS = os.environ.get('USE_HTTPS', 'false').lower() == 'true'

app = FastAPI(title="Hospital Booking API")

# CORS
origins = [
    "http://localhost",
    "http://localhost:5001",
    "http://127.0.0.1:5001",
    "http://humnoi.localhost",
    "http://demo.localhost", 
    "http://*.localhost",
    f"http://*.{DOMAIN}",
    f"https://*.{DOMAIN}" if USE_HTTPS else None
]
origins = [o for o in origins if o]  # กรอง None ออก

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=False,  # Set to False when using allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(event_types_router)
app.include_router(availability_router)
app.include_router(booking_router)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        db.execute(text("SET search_path TO public"))
        yield db
    finally:
        db.execute(text("SET search_path TO DEFAULT"))
        db.close()

# --- Pydantic Models ---
class SignupPayload(BaseModel):
    hospitalName: str
    subdomain: constr(pattern=r'^[a-z0-9-]+$')
    adminName: str
    adminEmail: EmailStr
    adminPhone: constr(pattern=r'^[0-9]{10}$')
    password: str
    plan: Literal['free', 'basic', 'professional']

# --- Universal URL Helper ---
def get_universal_url(subdomain: str, path: str = "/dashboard", params: dict = None) -> str:
    """
    สร้าง URL ที่ใช้ได้ทั้ง development และ production
    
    Development: http://localhost/dashboard?subdomain=xxx
    Production: https://xxx.yourdomain.com/dashboard
    """
    
    if params is None:
        params = {}
    
    # สร้าง query string
    query_params = []
    for key, value in params.items():
        query_params.append(f"{key}={value}")
    
    if ENVIRONMENT == 'development' or DOMAIN == 'localhost':
        # Development mode: ใช้ query parameter
        protocol = "https" if USE_HTTPS else "http"
        base_url = f"{protocol}://{DOMAIN}"
        
        # เพิ่ม port ถ้าไม่ใช่ default port
        if not USE_HTTPS and DOMAIN == 'localhost':
            # ใน development ปกติจะใช้ nginx ที่ port 80
            pass
        elif DOMAIN == 'localhost':
            base_url = f"{protocol}://{DOMAIN}"
        
        # เพิ่ม subdomain เป็น parameter
        query_params.insert(0, f"subdomain={subdomain}")
        
        query_string = "&".join(query_params) if query_params else ""
        return f"{base_url}{path}?{query_string}" if query_string else f"{base_url}{path}"
    
    else:
        # Production mode: ใช้ subdomain จริง
        protocol = "https" if USE_HTTPS else "http"
        base_url = f"{protocol}://{subdomain}.{DOMAIN}"
        
        query_string = "&".join(query_params) if query_params else ""
        return f"{base_url}{path}?{query_string}" if query_string else f"{base_url}{path}"

def create_tenant_setup(schema_name: str, db: Session):
    """สร้าง tenant schema, tables และข้อมูลเริ่มต้น"""
    
    try:
        # สร้าง schema
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        
        # ตั้งค่า search_path
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # สร้าง tables ด้วย SQL แทน SQLAlchemy (เพื่อให้ schema ถูกต้อง)
        db.execute(text('''
            CREATE TABLE availabilities (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                day_of_week VARCHAR(20) NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                timezone VARCHAR(50) DEFAULT 'Asia/Bangkok',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        db.execute(text('''
            CREATE TABLE event_types (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(50) NOT NULL UNIQUE,
                description TEXT,
                duration_minutes INTEGER NOT NULL DEFAULT 30,
                color VARCHAR(7) DEFAULT '#6366f1',
                is_active BOOLEAN DEFAULT true,
                availability_id INTEGER REFERENCES availabilities(id),
                buffer_before_minutes INTEGER DEFAULT 0,
                buffer_after_minutes INTEGER DEFAULT 0,
                max_bookings_per_day INTEGER,
                min_notice_hours INTEGER DEFAULT 4,
                max_advance_days INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        db.execute(text('''
            CREATE TABLE providers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                title VARCHAR(20),
                department VARCHAR(100),
                is_active BOOLEAN DEFAULT true,
                public_booking_url VARCHAR(100),
                bio TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        db.execute(text('''
            CREATE TABLE patients (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                phone_number VARCHAR(20),
                email VARCHAR(120),
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        db.execute(text('''
            CREATE TABLE date_overrides (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                is_unavailable BOOLEAN DEFAULT false,
                custom_start_time TIME,
                custom_end_time TIME,
                reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        db.execute(text('''
            CREATE TABLE appointments (
                id SERIAL PRIMARY KEY,
                patient_id INTEGER REFERENCES patients(id),
                event_type_id INTEGER REFERENCES event_types(id),
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'confirmed',
                guest_name VARCHAR(100),
                guest_email VARCHAR(120), 
                guest_phone VARCHAR(20),
                notes VARCHAR(500),
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))
        
        # สร้างข้อมูลเริ่มต้น
        # 1. สร้าง availability templates (รูปแบบเวลาทำงาน)
        db.execute(text("""
            INSERT INTO availabilities (name, description, day_of_week, start_time, end_time, timezone, is_active, created_at)
            VALUES 
                ('จันทร์-ศุกร์ (08:30-16:30)', 'เวลาทำการปกติวันธรรมดา', 'MONDAY', '08:30', '16:30', 'Asia/Bangkok', true, NOW()),
                ('จันทร์-ศุกร์ (08:30-16:30)', 'เวลาทำการปกติวันธรรมดา', 'TUESDAY', '08:30', '16:30', 'Asia/Bangkok', true, NOW()),
                ('จันทร์-ศุกร์ (08:30-16:30)', 'เวลาทำการปกติวันธรรมดา', 'WEDNESDAY', '08:30', '16:30', 'Asia/Bangkok', true, NOW()),
                ('จันทร์-ศุกร์ (08:30-16:30)', 'เวลาทำการปกติวันธรรมดา', 'THURSDAY', '08:30', '16:30', 'Asia/Bangkok', true, NOW()),
                ('จันทร์-ศุกร์ (08:30-16:30)', 'เวลาทำการปกติวันธรรมดา', 'FRIDAY', '08:30', '16:30', 'Asia/Bangkok', true, NOW()),
                ('เสาร์-อาทิตย์ (09:00-12:00)', 'เวลาทำการวันหยุด', 'SATURDAY', '09:00', '12:00', 'Asia/Bangkok', true, NOW()),
                ('เสาร์-อาทิตย์ (09:00-12:00)', 'เวลาทำการวันหยุด', 'SUNDAY', '09:00', '12:00', 'Asia/Bangkok', true, NOW())
        """))
        
        db.commit()
        
        # 2. หา availability_id แรกที่สร้าง
        first_availability_id = db.execute(text("SELECT id FROM availabilities ORDER BY id LIMIT 1")).scalar()
        
        # 3. สร้าง event types ที่อ้างอิงไปยัง availability
        db.execute(text(f"""
            INSERT INTO event_types (name, slug, description, duration_minutes, color, is_active, buffer_before_minutes, buffer_after_minutes, min_notice_hours, max_advance_days, availability_id)
            VALUES 
                ('ตรวจสุขภาพทั่วไป', 'general-checkup', 'การตรวจสุขภาพพื้นฐานและให้คำปรึกษา', 30, '#6366f1', true, 10, 10, 4, 60, {first_availability_id}),
                ('ปรึกษาแพทย์เฉพาะทาง', 'specialist-consult', 'การปรึกษาแพทย์ผู้เชี่ยวชาญ', 45, '#10b981', true, 15, 15, 24, 90, {first_availability_id}),
                ('ฉีดวัคซีน', 'vaccination', 'บริการฉีดวัคซีนป้องกันโรค', 15, '#f59e0b', true, 5, 5, 4, 30, {first_availability_id}),
                ('ตรวจประจำปี', 'annual-checkup', 'การตรวจสุขภาพประจำปีแบบครบถ้วน', 60, '#ef4444', true, 15, 15, 48, 120, {first_availability_id})
        """))
        
        # 4. สร้าง providers (ถ้าจำเป็นในอนาคต)
        db.execute(text("""
            INSERT INTO providers (name, title, department, is_active, public_booking_url, bio)
            VALUES 
                ('นพ.สมชาย ใจดี', 'นพ.', 'แพทย์ทั่วไป', true, 'dr-somchai', 'แพทย์ผู้เชี่ยวชาญด้านการดูแลสุขภาพทั่วไป')
        """))
        
        # 5. สร้างผู้ป่วยตัวอย่าง
        db.execute(text("""
            INSERT INTO patients (name, phone_number, email)
            VALUES 
                ('สมชาย ใจดี', '0812345678', 'somchai@email.com'),
                ('สมหญิง สวยงาม', '0823456789', 'somying@email.com'),
                ('น้องมินิ สุขใจ', '0834567890', 'mini@email.com')
        """))
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        raise Exception(f"Failed to create tenant setup: {str(e)}")
    finally:
        # Reset search path
        db.execute(text('SET search_path TO public'))

# --- API Endpoints ---
@app.post("/api/register")
def register_hospital(payload: SignupPayload, db: Session = Depends(get_db)):
    """Hospital registration with universal URL handling"""
    
    # Check duplicates
    if db.query(models.Hospital).filter_by(subdomain=payload.subdomain).first():
        raise HTTPException(status_code=409, detail="Subdomain already exists.")
    if db.query(models.User).filter_by(email=payload.adminEmail).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    try:
        schema_name = "tenant_" + "".join(filter(str.isalnum, payload.subdomain))
        
        # Create hospital
        new_hospital = models.Hospital(
            name=payload.hospitalName, 
            subdomain=payload.subdomain, 
            schema_name=schema_name
        )
        db.add(new_hospital)
        db.flush()

        # Create admin user
        new_user = models.User(
            name=payload.adminName,
            email=payload.adminEmail,
            phone_number=payload.adminPhone,
            hospital_id=new_hospital.id
        )
        new_user.set_password(payload.password)
        db.add(new_user)

        if payload.plan == 'free':
            db.commit()
            
            # Create tenant schema and tables
            create_tenant_setup(schema_name, db)
            
            # Generate universal dashboard URL
            dashboard_url = get_universal_url(
                subdomain=new_hospital.subdomain,
                path="/dashboard",
                params={"new": "true"}
            )
            
            return {
                "success": True,
                "message": "Free trial account created successfully.",
                "url": dashboard_url
            }
        
        elif payload.plan in PRICE_IDS:
            customer = stripe.Customer.create(
                email=new_user.email, 
                name=new_hospital.name,
                metadata={'hospital_id': new_hospital.id}
            )
            new_hospital.stripe_customer_id = customer.id
            
            # Generate URLs for Stripe
            success_url = get_universal_url(
                subdomain=new_hospital.subdomain,
                path="/dashboard",
                params={"new": "true"}
            )
            
            cancel_url = get_universal_url(
                subdomain="",  # หน้าหลัก
                path="/",
                params={"cancelled": "true"}
            )
            
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                line_items=[{'price': PRICE_IDS[payload.plan], 'quantity': 1}],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                subscription_data={'trial_period_days': 14}
            )
            
            db.commit()
            
            # Create tenant schema and tables for paid plans too
            create_tenant_setup(schema_name, db)
            
            return {"checkout_url": checkout_session.url}
        
        else:
            raise HTTPException(status_code=400, detail="Invalid plan selected.")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health")
def health_check():
    """System health check"""
    return {
        "status": "ok",
        "environment": ENVIRONMENT,
        "domain": DOMAIN,
        "use_https": USE_HTTPS
    }

@app.post("/api/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook handler"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        hospital = db.query(models.Hospital).filter_by(stripe_customer_id=customer_id).first()
        if hospital:
            hospital.stripe_subscription_id = subscription_id
            db.commit()
            print(f"Subscription {subscription_id} created for hospital {hospital.name}")

    return {"status": "success"}