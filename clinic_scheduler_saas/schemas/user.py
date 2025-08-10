from pydantic import BaseModel, EmailStr, ConfigDict

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    organization_name: str

class UserRead(UserBase):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)