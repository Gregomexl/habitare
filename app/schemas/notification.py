import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel
from app.models.notification import NotificationChannel, NotificationStatus


class NotificationResponse(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    channel: NotificationChannel
    recipient_id: uuid.UUID | None
    status: NotificationStatus
    payload: dict[str, Any]
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
