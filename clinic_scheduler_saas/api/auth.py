from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from core.database import get_db
from services import auth_service
from schemas import user as user_schema, token as token_schema
from models import user as user_model

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=user_schema.UserRead)
def register(user_in: user_schema.UserCreate, db: Session = Depends(get_db)):
    return auth_service.create_user_and_org(db=db, user_in=user_in)

@router.post("/login", response_model=token_schema.Token)
def login_for_access_token(
    db: Session = Depends(get_db), 
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = db.query(user_model.User).filter(user_model.User.email == form_data.username).first()
    if not user or not auth_service.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )
    access_token = auth_service.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}