import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class VisitorCreate(BaseModel):
    name: str
    email: EmailStr | None = None  # validated format; used for email dedup
    phone: str | None = None
    vehicle_plate: str | None = None


class VisitorUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    vehicle_plate: str | None = None


class VisitorResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    photo_url: str | None
    vehicle_plate: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
