"""Invitation model — pass link token for both pre-reg and walk-in flows."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import UUID, String, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class InvitationStatus(str, Enum):
    PENDING = "pending"   # created, not yet opened
    VIEWED = "viewed"     # visitor opened the pass link
    EXPIRED = "expired"   # past expires_at or manually revoked


class Invitation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    sent_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Signed token used in the pass link URL — /pass/{token}
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        SAEnum(InvitationStatus, name="invitationstatus"), nullable=False, default=InvitationStatus.PENDING
    )
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    def __repr__(self) -> str:
        return f"<Invitation(id={self.id}, status={self.status})>"
