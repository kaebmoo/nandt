from fastapi import APIRouter, Depends, HTTPException
from schemas.booking import BookingCreate
from services import cal_com_service, auth_service
from models.user import User

router = APIRouter(prefix="/bookings", tags=["Bookings"])

@router.get("/")
async def get_user_bookings(current_user: User = Depends(auth_service.get_current_user)):
    if not current_user.organization.cal_com_api_key:
        raise HTTPException(status_code=403, detail="Cal.com API Key is not set")
    success, data = await cal_com_service.get_bookings(current_user.organization.cal_com_api_key)
    if not success:
        raise HTTPException(status_code=400, detail=data)
    return data

@router.post("/")
async def create_new_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(auth_service.get_current_user)
):
    if not current_user.organization.cal_com_api_key:
        raise HTTPException(status_code=403, detail="Cal.com API Key is not set")
    success, data = await cal_com_service.create_booking(
        api_key=current_user.organization.cal_com_api_key,
        booking_data=booking_data.dict()
    )
    if not success:
        raise HTTPException(status_code=400, detail=data)
    return data