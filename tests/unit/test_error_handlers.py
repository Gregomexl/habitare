"""Unit tests: error envelope shape and request ID middleware."""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


@pytest.mark.asyncio
async def test_request_id_generated_when_not_provided():
    """Response must include X-Request-ID when client sends none."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert "x-request-id" in resp.headers
    # Should be a valid UUID
    uuid.UUID(resp.headers["x-request-id"])


@pytest.mark.asyncio
async def test_request_id_echoed_when_provided():
    """Response must echo back the client-supplied X-Request-ID."""
    from app.main import app
    custom_id = "my-custom-request-id-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_http_exception_returns_error_envelope():
    """HTTPException should return structured error envelope."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users/me")  # no auth → 401
    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "HTTP_401"
    assert "request_id" in body["error"]


@pytest.mark.asyncio
async def test_unknown_route_returns_error_envelope():
    """Unknown route (404) must return error envelope, not Starlette default."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "HTTP_404"


@pytest.mark.asyncio
async def test_validation_error_returns_error_envelope():
    """Invalid request body should return VALIDATION_ERROR envelope."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "pw"},  # missing tenant_id
        )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["detail"], list)


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429_after_limit():
    """6th login attempt in same minute should return 429 with error envelope."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            await client.post(
                "/api/v1/auth/login",
                json={"email": "x@x.com", "password": "pw", "tenant_id": "00000000-0000-0000-0000-000000000000"},
            )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@x.com", "password": "pw", "tenant_id": "00000000-0000-0000-0000-000000000000"},
        )
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "request_id" in body["error"]
