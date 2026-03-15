"""
SQLAlchemy Base Models and Mixins
Using SQLAlchemy 2.0 async patterns with proper type annotations
"""
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import UUID, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """
    Base model with AsyncAttrs for proper async relationship loading.

    AsyncAttrs is required for SQLAlchemy 2.0 async ORM to properly
    load relationships using awaitable attributes.
    """
    pass


class TenantMixin:
    """
    Mixin for tenant-scoped models.

    Adds tenant_id column to enforce multi-tenancy at the model level.
    Works with Row-Level Security (RLS) policies for database-level isolation.
    """
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant (property) identifier for multi-tenancy"
    )


class TimestampMixin:
    """
    Mixin for automatic timestamp tracking.

    Adds created_at and updated_at columns with automatic management.
    """
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when record was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        server_onupdate=func.now(),
        nullable=False,
        comment="Timestamp when record was last updated"
    )
