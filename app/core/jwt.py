"""JWT creation and validation.

Access tokens: HS256, 30-min default lifetime (configurable via settings).
Payload: sub (user_id str), tenant_id (str), role (str), exp, iat.
iat is included for audit purposes but not validated beyond PyJWT built-ins.
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    expire_minutes: int | None = None,
) -> str:
    """Create a signed JWT access token."""
    if expire_minutes is None:
        expire_minutes = settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTP 401 on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        if not all(k in payload for k in ("sub", "tenant_id", "role")):
            raise ValueError("Missing required claims")
        return payload
    except Exception as exc:
        logger.debug("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
