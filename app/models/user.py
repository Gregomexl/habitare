"""
User Model
Represents users in the system (tenant users, property admins, super admins)
"""
from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import UUID, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin


class UserRole(str, Enum):
    """
    User role enumeration.

    - TENANT_USER: Resident/tenant who uses visitor management features
    - PROPERTY_ADMIN: Property manager/administrator
    - SUPER_ADMIN: System administrator with full access
    """
    TENANT_USER = "tenant_user"
    PROPERTY_ADMIN = "property_admin"
    SUPER_ADMIN = "super_admin"


class User(Base, TenantMixin, TimestampMixin):
    """
    User model for authentication and authorization.

    Supports multiple authentication methods:
    - Email/password (password_hash can be NULL for social/SSO users)
    - Social login (Google, Apple)
    - Enterprise SSO (Microsoft, Okta)
    """
    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="User unique identifier"
    )

    # Authentication
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User email address (unique per tenant)"
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Argon2id password hash (NULL for social/SSO users)"
    )

    # User Information
    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User's full name"
    )

    unit_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Unit/apartment number for tenant users"
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="User phone number"
    )

    # Role and Status
    role: Mapped[UserRole] = mapped_column(
        nullable=False,
        comment="User role in the system"
    )

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether email has been verified"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="Whether user account is active"
    )

    # Tracking
    last_login_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Last successful login timestamp"
    )

    # Indexes and Constraints
    __table_args__ = (
        # Unique constraint: one email per tenant
        # Note: SQLAlchemy will create this as a unique index
        # UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
