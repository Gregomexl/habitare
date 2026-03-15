"""
FastAPI Dependency Injection
Database session and authentication dependencies.
"""
import uuid
from dataclasses import dataclass
from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.jwt import decode_token
from app.models.user import UserRole


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency with automatic cleanup."""
    async with async_session() as session:
        yield session


AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def set_rls(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set session-local RLS variable. Must be called inside an active transaction.

    asyncpg does not support parameterized SET LOCAL; UUID str() is safe to
    interpolate because uuid.UUID.__str__() always produces a well-formed UUID
    with no SQL special characters.
    """
    await db.execute(sql_text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))


@dataclass
class TokenData:
    """Claims extracted from a validated JWT access token."""
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenData:
    """Decode JWT. No DB hit — RLS is managed per-endpoint inside db.begin() blocks.

    Deactivated users retain access until the token expires (max 30 min).
    A token blocklist is out of scope for Phase 3.
    """
    payload = decode_token(token)
    try:
        return TokenData(
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            role=payload["role"],
        )
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentUserDep = Annotated[TokenData, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """Dependency factory: raises 403 if current user's role is not in `roles`.

    Usage:
        async def my_endpoint(current_user: RequireAdminDep, ...): ...

    Note: require_role() returns the inner async function (not Depends). Wrap in
    Annotated[TokenData, Depends(...)] to create typed aliases (see below).
    """
    async def check(current_user: CurrentUserDep) -> TokenData:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return check


RequireAdminDep = Annotated[TokenData, Depends(require_role(UserRole.PROPERTY_ADMIN, UserRole.SUPER_ADMIN))]
RequireSuperAdminDep = Annotated[TokenData, Depends(require_role(UserRole.SUPER_ADMIN))]
