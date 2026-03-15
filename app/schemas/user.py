import uuid
from pydantic import BaseModel
from app.models.user import UserRole


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    tenant_id: uuid.UUID
    is_active: bool
