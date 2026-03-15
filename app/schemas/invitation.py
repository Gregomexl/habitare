import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.invitation import InvitationStatus


class InvitationCreate(BaseModel):
    visit_id: uuid.UUID
    sent_to_email: EmailStr | None = None


class InvitationResponse(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    token: str
    status: InvitationStatus
    sent_to_email: str | None
    expires_at: datetime
    pass_link: str | None = None  # populated by endpoint

    model_config = {"from_attributes": True}


class PassLinkResponse(BaseModel):
    visitor_name: str
    host_name: str | None  # null for walk-ins with no host
    scheduled_at: datetime | None
    qr_code_url: str
    expires_at: datetime
