import uuid
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    full_name: str | None
    phone_number: str | None
    unit_number: str | None
    role: UserRole
    tenant_id: uuid.UUID
    is_active: bool


class UserUpdateMe(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    phone_number: str | None = None
    unit_number: str | None = None


class UserCreateResponse(UserResponse):
    temp_password: str  # returned once, never stored plaintext


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None
