import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    subscription_tier: str
    created_at: datetime

    model_config = {"from_attributes": True}


SubscriptionTier = Literal["basic", "pro", "enterprise"]


class TenantCreate(BaseModel):
    name: str
    slug: str
    subscription_tier: SubscriptionTier = "basic"
    settings: dict = {}


class TenantUpdate(BaseModel):
    name: str | None = None
    subscription_tier: SubscriptionTier | None = None
    settings: dict | None = None
