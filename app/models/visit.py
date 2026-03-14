"""Visit model — one record per visit event, tracks full lifecycle."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import UUID, DateTime, String, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class VisitStatus(str, Enum):
    SCHEDULED = "scheduled"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"


class Visit(Base, TenantMixin, TimestampMixin):
    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id"), nullable=False, index=True
    )
    # nullable — walk-ins may have no specific host
    host_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[VisitStatus] = mapped_column(
        SAEnum(VisitStatus, name="visitstatus"), nullable=False, default=VisitStatus.SCHEDULED
    )
    # nullable — null for walk-ins
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Visit(id={self.id}, status={self.status})>"
