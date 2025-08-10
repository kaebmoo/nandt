# hospital-booking/fastapi_app/app/main.py

import os
import stripe
from fastapi import FastAPI, Depends, Header, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, constr
from typing import Literal

# Import models from Flask app's location
# This is a common pattern for sharing models between Flask and FastAPI in the same project
import sys
sys.path.append('../../flask_app')
from app import models

# --- Database Setup ---
from app.database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine)

# --- Stripe Configuration ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
PRICE_IDS = {
    'basic': 'price_1PgZqgP8aZg8A7z6o9y7x8z9', # ตัวอย่าง: แก้ไขด้วย ID จริง
    'professional': 'price_1PgZqgP8aZg8A7z6a1b2c3d4' # ตัวอย่าง: แก้ไขด้วย ID จริง
}
YOUR_DOMAIN = 'http://localhost'

app = FastAPI(title="Hospital Booking API")

# --- Dependency to get DB session ---
def get_db():
    db = SessionLocal()
    try:
        db.execute("SET search_path TO public")
        yield db
    finally:
        db.close()

# --- Pydantic Models for Validation ---
class SignupPayload(BaseModel):
    hospitalName: str
    subdomain: constr(regex=r'^[a-z0-9-]+$')
    adminName: str
    adminEmail: EmailStr
    adminPhone: constr(regex=r'^[0-9]{10}$')
    password: str
    plan: Literal['free', 'basic', 'professional']

# --- API Endpoints ---
@app.post("/api/register")
def register_hospital(payload: SignupPayload, db: Session = Depends(get_db)):
    """
    Handles new hospital registration.
    """
    # Check for existing subdomain or email
    if db.query(models.Hospital).filter_by(subdomain=payload.subdomain).first():
        raise HTTPException(status_code=409, detail="Subdomain already exists.")
    if db.query(models.User).filter_by(email=payload.adminEmail).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    try:
        schema_name = "tenant_" + "".join(filter(str.isalnum, payload.subdomain))
        
        new_hospital = models.Hospital(name=payload.hospitalName, subdomain=payload.subdomain, schema_name=schema_name)
        db.add(new_hospital)
        db.flush()

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
            return {
                "success": True,
                "message": "Free trial account created successfully.",
                "url": f"http://{new_hospital.subdomain}.localhost/dashboard?new=true"
            }
        
        elif payload.plan in PRICE_IDS:
            customer = stripe.Customer.create(
                email=new_user.email, name=new_hospital.name,
                metadata={'hospital_id': new_hospital.id}
            )
            new_hospital.stripe_customer_id = customer.id
            
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                line_items=[{'price': PRICE_IDS[payload.plan], 'quantity': 1}],
                mode='subscription',
                success_url=f"http://{new_hospital.subdomain}.localhost/dashboard?new=true",
                cancel_url=f"{YOUR_DOMAIN}/",
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
def health_check(x_tenant_id: str | None = Header(default=None)):
    # This endpoint remains for checking tenant connections
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required.")
    
    db = SessionLocal()
    try:
        db.execute(f'SET search_path TO "tenant_{x_tenant_id}", public')
        return {"status": "ok", "message": f"Successfully connected to tenant: {x_tenant_id}"}
    except Exception:
        raise HTTPException(status_code=404, detail=f"Tenant '{x_tenant_id}' not found.")
    finally:
        db.close()