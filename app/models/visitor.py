"""Visitor model — reusable guest profile, deduped by email within tenant."""
import uuid

from sqlalchemy import UUID, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Visitor(Base, TenantMixin, TimestampMixin):
    __tablename__ = "visitors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vehicle_plate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        # Partial unique index: one email per tenant, only when email is not null
        Index(
            "uq_visitors_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Visitor(id={self.id}, name={self.name})>"
