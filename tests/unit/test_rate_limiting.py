"""Unit tests for rate limiting key function."""
import uuid
import pytest
from fastapi import Request


def _make_request(authorization: str = "", client_host: str = "127.0.0.1") -> Request:
    """Build a minimal mock Request for testing."""
    scope = {
        "type": "http",
        "headers": [(b"authorization", authorization.encode())] if authorization else [],
        "client": (client_host, 12345),
        "method": "GET",
        "path": "/test",
        "query_string": b"",
    }
    return Request(scope)


def test_get_tenant_key_returns_tenant_id_from_valid_jwt():
    """Should return tenant_id string when a valid JWT is present."""
    import jwt
    from app.core.config import settings
    from app.core.limiter import get_tenant_key

    tenant_id = str(uuid.uuid4())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "tenant_id": tenant_id, "role": "tenant_user"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    request = _make_request(authorization=f"Bearer {token}")
    result = get_tenant_key(request)
    assert result == tenant_id


def test_get_tenant_key_falls_back_to_ip_when_no_header():
    """Should return IP address when no Authorization header present."""
    from app.core.limiter import get_tenant_key
    request = _make_request(client_host="10.0.0.1")
    result = get_tenant_key(request)
    assert result == "10.0.0.1"


def test_get_tenant_key_falls_back_to_ip_when_jwt_malformed():
    """Should return IP address when Authorization header has invalid JWT."""
    from app.core.limiter import get_tenant_key
    request = _make_request(authorization="Bearer not.a.valid.jwt", client_host="10.0.0.2")
    result = get_tenant_key(request)
    assert result == "10.0.0.2"


def test_get_tenant_key_falls_back_to_ip_when_no_tenant_id_claim():
    """Should return IP address when JWT is valid but has no tenant_id claim."""
    import jwt
    from app.core.config import settings
    from app.core.limiter import get_tenant_key

    token = jwt.encode(
        {"sub": str(uuid.uuid4())},  # no tenant_id
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    request = _make_request(authorization=f"Bearer {token}")
    result = get_tenant_key(request)
    assert result == "127.0.0.1"
