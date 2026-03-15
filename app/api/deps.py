"""
FastAPI Dependency Injection
Database session and authentication dependencies
"""
import uuid
from typing import Annotated, AsyncGenerator
from fastapi import Depends, Header, HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency with automatic cleanup.

    Uses yield pattern for automatic session closing after request completion.
    This is the FastAPI best practice for managing database sessions.
    """
    async with async_session() as session:
        yield session


# Type alias for cleaner endpoint signatures
AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


# Temporary stub — replace with JWT-based extraction when Phase 1 auth is complete
async def get_tenant_id(
    x_tenant_id: str = Header(..., description="Tenant UUID (temporary — will be JWT claim)")
) -> uuid.UUID:
    """Extract tenant_id. Phase 2 stub: reads from X-Tenant-Id header.
    Replace with JWT payload extraction when auth endpoints are complete."""
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")


TenantIdDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


async def set_rls(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set session-local RLS variable. Must be called inside an active transaction."""
    await db.execute(sql_text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
