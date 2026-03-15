import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.qr_code import QRCodeType


class QRCodeResponse(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    code: uuid.UUID
    type: QRCodeType
    valid_from: datetime
    valid_until: datetime
    used_at: datetime | None
    is_revoked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QRScanResponse(BaseModel):
    visit_id: uuid.UUID
    visitor_name: str
    checked_in_at: datetime
