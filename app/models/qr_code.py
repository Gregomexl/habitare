"""QRCode model — one code per visit, type determines validation behavior."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import UUID, Boolean, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class QRCodeType(str, Enum):
    ONE_TIME = "one_time"           # walk-in: single scan, 30-min window
    TIME_BOUNDED = "time_bounded"   # pre-reg: multi-scan within time window


class QRCode(Base, TenantMixin, TimestampMixin):
    __tablename__ = "qr_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    # The scannable token — encoded in the QR image as a raw UUID string
    # unique=True creates a named index; no additional UniqueConstraint needed
    code: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True, index=False
    )
    type: Mapped[QRCodeType] = mapped_column(
        SAEnum(QRCodeType, name="qrcodetype"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(nullable=False)
    valid_until: Mapped[datetime] = mapped_column(nullable=False)
    # Set on first scan for ONE_TIME; used for replay detection
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<QRCode(code={self.code}, type={self.type})>"
