"""Notification model — audit log of all staff-facing notifications."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import UUID, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class NotificationChannel(str, Enum):
    EMAIL = "email"
    WEBSOCKET = "websocket"


class NotificationStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class Notification(Base, TenantMixin, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, name="notificationchannel"), nullable=False
    )
    # nullable — null for broadcast WS or when host is absent
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notificationstatus"), nullable=False, default=NotificationStatus.QUEUED
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, channel={self.channel}, status={self.status})>"
