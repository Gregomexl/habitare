import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.visit import VisitStatus


class VisitCreate(BaseModel):
    visitor_id: uuid.UUID
    purpose: str
    host_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None


class VisitResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    visitor_id: uuid.UUID
    host_id: uuid.UUID | None
    purpose: str
    status: VisitStatus
    scheduled_at: datetime | None
    checked_in_at: datetime | None
    checked_out_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
