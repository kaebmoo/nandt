# api/organizations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from models import user as user_model
from schemas import organization as org_schema
from services import auth_service
from services import cal_com_service

router = APIRouter(prefix="/organization", tags=["Organization"])

@router.put("/api_key")
def update_api_key(
    api_key_data: org_schema.ApiKeyUpdate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user)
):
    """
    Endpoint สำหรับให้ผู้ใช้บันทึกหรืออัปเดต Cal.com API Key
    ขององค์กรตัวเอง
    """
    organization = current_user.organization
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    organization.cal_com_api_key = api_key_data.api_key
    db.add(organization)
    db.commit()
    db.refresh(organization)

    return {"message": "API Key updated successfully"}

@router.get("/event-types")
async def get_organization_event_types(
    current_user: user_model.User = Depends(auth_service.get_current_user)
):
    """Endpoint สำหรับดึง Event Types ทั้งหมดจาก Cal.com ขององค์กร"""
    if not current_user.organization or not current_user.organization.cal_com_api_key:
        raise HTTPException(status_code=403, detail="API Key not set")

    success, data = await cal_com_service.get_event_types(
        api_key=current_user.organization.cal_com_api_key
    )
    if not success:
        raise HTTPException(status_code=400, detail=data)
    
    return data