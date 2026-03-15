"""Rate limiting: single slowapi Limiter with tenant-keyed and IP-keyed strategies.

Context7 confirmed patterns:
- Single Limiter instance registered on app.state.limiter
- Per-route key_func override: @limiter.limit("5/minute", key_func=get_remote_address)
- SlowAPIASGIMiddleware (pure ASGI) preferred over SlowAPIMiddleware (BaseHTTPMiddleware)
"""
import jwt as pyjwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_tenant_key(request: Request) -> str:
    """Rate-limit key: tenant_id from JWT, falls back to IP.

    Uses jwt.decode with verify_signature=False — we only need the tenant_id
    claim for bucketing, not for authentication. decode_token() from jwt.py
    raises HTTPException which is the wrong contract for a key function.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = pyjwt.decode(
                auth.removeprefix("Bearer "),
                options={"verify_signature": False},
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return str(tenant_id)
        except Exception:
            pass
    return get_remote_address(request)


# Single limiter instance — registered on app.state.limiter in main.py.
# Auth endpoints override key_func=get_remote_address at the decorator level.
limiter = Limiter(key_func=get_tenant_key)
