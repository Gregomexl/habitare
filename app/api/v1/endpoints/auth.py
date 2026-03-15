"""Auth endpoints: login, refresh, logout."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.core.config import settings
from app.core.jwt import create_access_token
from app.core.security import verify_password
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _token_response(user_id, tenant_id, role, raw_refresh: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id, tenant_id, role),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSessionDep) -> TokenResponse:
    """Authenticate with email + password + tenant_id. Returns JWT pair."""
    async with db.begin():
        await set_rls(db, body.tenant_id)

        result = await db.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()

        # Deliberate: same error for not-found, inactive, and wrong password — no oracle.
        _invalid = HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if not user or not user.is_active or not user.password_hash:
            raise _invalid
        if not verify_password(body.password, user.password_hash):
            raise _invalid

        user.last_login_at = datetime.now(timezone.utc)

        raw = secrets.token_urlsafe(32)
        rt = RefreshToken(
            user_id=user.id,
            tenant_id=body.tenant_id,
            token_hash=_hash(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(rt)
        await db.flush()

        return _token_response(user.id, body.tenant_id, user.role.value, raw)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSessionDep) -> TokenResponse:
    """Rotate refresh token. Old token is revoked; new pair is issued."""
    token_hash = _hash(body.refresh_token)
    now = datetime.now(timezone.utc)

    async with db.begin():
        # No RLS needed: refresh_tokens table has no RLS policy.
        # See spec: isolation is via token_hash uniqueness + user_id FK.
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        rt = result.scalar_one_or_none()

        if rt and rt.revoked_at is not None:
            logger.warning(
                "Revoked refresh token presented for user %s — possible theft", rt.user_id
            )

        if not rt or rt.revoked_at is not None or rt.expires_at <= now:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Look up user (within tenant RLS) to get current role.
        await set_rls(db, rt.tenant_id)
        user_result = await db.execute(select(User).where(User.id == rt.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Rotate: revoke old, create new.
        rt.revoked_at = now
        new_raw = secrets.token_urlsafe(32)
        new_rt = RefreshToken(
            user_id=rt.user_id,
            tenant_id=rt.tenant_id,
            token_hash=_hash(new_raw),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(new_rt)
        await db.flush()

        return _token_response(user.id, rt.tenant_id, user.role.value, new_raw)


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> None:
    """Revoke the provided refresh token. Idempotent — missing token is silently ignored."""
    if not body.refresh_token:
        return

    token_hash = _hash(body.refresh_token)
    now = datetime.now(timezone.utc)

    async with db.begin():
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == current_user.user_id,  # scope to current user
            )
        )
        rt = result.scalar_one_or_none()
        if rt and rt.revoked_at is None:
            rt.revoked_at = now
