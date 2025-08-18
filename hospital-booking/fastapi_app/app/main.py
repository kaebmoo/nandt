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
from datetime import time

load_dotenv()

# Import models
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'flask_app', 'app'))
from shared_db import models
from shared_db.database import SessionLocal, engine

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
    """สร้าง tenant schema, tables และข้อมูลเริ่มต้นด้วย SQLAlchemy Objects"""
    
    try:
        # 1. สร้าง Schema
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        
        # 2. ตั้งค่า Search Path ชั่วคราว
        db.execute(text(f'SET search_path TO "{schema_name}", public'))
        
        # 3. สร้างตารางทั้งหมดจาก models.py (วิธีที่ถูกต้องและยั่งยืน)
        models.TenantBase.metadata.create_all(bind=db.get_bind())
        
        # 4. สร้างข้อมูลเริ่มต้นด้วย SQLAlchemy Objects (แทนที่ SQL INSERT)
        
        # --- สร้าง Availability Template เริ่มต้น ---
        default_template = models.AvailabilityTemplate(
            name="เวลาทำการเริ่มต้น",
            description="จันทร์-ศุกร์ (08:30-16:30)",
            timezone="Asia/Bangkok"
        )
        db.add(default_template)
        db.flush() # ส่งข้อมูลไป DB เพื่อให้ได้ template ID

        # --- สร้าง Availability (วันและเวลา) สำหรับ Template นั้น ---
        working_days = [
            models.DayOfWeek.MONDAY, models.DayOfWeek.TUESDAY, 
            models.DayOfWeek.WEDNESDAY, models.DayOfWeek.THURSDAY, 
            models.DayOfWeek.FRIDAY
        ]
        for day in working_days:
            availability = models.Availability(
                template_id=default_template.id,
                day_of_week=day,
                start_time=time(8, 30),
                end_time=time(16, 30)
            )
            db.add(availability)

        # --- สร้าง Event Types เริ่มต้น โดยอ้างอิงถึง Template ID ---
        event_types_data = [
            {'name': 'ตรวจสุขภาพทั่วไป', 'slug': 'general-checkup', 'duration_minutes': 30, 'color': '#6366f1'},
            {'name': 'ปรึกษาแพทย์เฉพาะทาง', 'slug': 'specialist-consult', 'duration_minutes': 45, 'color': '#10b981'},
            {'name': 'ฉีดวัคซีน', 'slug': 'vaccination', 'duration_minutes': 15, 'color': '#f59e0b'},
            {'name': 'ตรวจประจำปี', 'slug': 'annual-checkup', 'duration_minutes': 60, 'color': '#ef4444'}
        ]
        for data in event_types_data:
            event_type = models.EventType(
                name=data['name'],
                slug=data['slug'],
                duration_minutes=data['duration_minutes'],
                color=data['color'],
                template_id=default_template.id # อ้างอิงถึง Template ที่สร้าง
            )
            db.add(event_type)

        # --- สร้าง Provider ตัวอย่าง ---
        provider = models.Provider(
            name='นพ.สมชาย ใจดี',
            title='นพ.',
            department='แพทย์ทั่วไป',
            public_booking_url='dr-somchai',
            bio='แพทย์ผู้เชี่ยวชาญด้านการดูแลสุขภาพทั่วไป'
        )
        db.add(provider)

        # --- สร้าง Patient ตัวอย่าง ---
        patients_data = [
            {'name': 'สมชาย ใจดี', 'phone_number': '0812345678', 'email': 'somchai@email.com'},
            {'name': 'สมหญิง สวยงาม', 'phone_number': '0823456789', 'email': 'somying@email.com'}
        ]
        for data in patients_data:
            patient = models.Patient(**data)
            db.add(patient)

        # 5. Commit ข้อมูลทั้งหมดในครั้งเดียว
        db.commit()
        
    except Exception as e:
        db.rollback()
        # เพิ่มการแสดง Error ที่ละเอียดขึ้นเพื่อช่วยในการ Debug
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to create tenant setup: {str(e)}")
    finally:
        # 6. Reset search path กลับเป็นปกติเสมอ
        db.execute(text('SET search_path TO public'))
        db.commit()


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