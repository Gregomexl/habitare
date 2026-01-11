"""
Tenant Model
Represents properties/buildings in the multi-tenant system
"""
from datetime import datetime
import uuid

from sqlalchemy import UUID, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    """
    Tenant model representing properties/buildings.

    Each tenant is a separate property or building with its own
    set of users, visitors, and access control policies.
    """
    __tablename__ = "tenants"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Tenant unique identifier"
    )

    # Tenant Information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Property/building name"
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="URL-friendly identifier (e.g., 'sunset-towers')"
    )

    # Subscription and Configuration
    subscription_tier: Mapped[str] = mapped_column(
        String(50),
        default="basic",
        server_default="basic",
        nullable=False,
        comment="Subscription plan (basic, pro, enterprise)"
    )

    settings: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
        comment="Tenant-specific settings and preferences (JSON)"
    )

    # Soft Delete Support
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Soft delete timestamp (NULL if active)"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"
