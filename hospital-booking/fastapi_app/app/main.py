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
sys.path.append('flask_app/app')
import models 

from .database import SessionLocal, engine

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
    f"http://*.{DOMAIN}",
    f"https://*.{DOMAIN}" if USE_HTTPS else None
]
origins = [o for o in origins if o]  # กรอง None ออก

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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