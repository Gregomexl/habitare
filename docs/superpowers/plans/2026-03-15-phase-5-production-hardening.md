# Phase 5 — Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Habitare API for production by wiring real email delivery (Resend via httpx), adding slowapi rate limiting, a structured error envelope, a pure-ASGI request-ID middleware, and configurable CORS.

**Architecture:** All cross-cutting concerns (rate limiting, request ID, error envelope) are handled at the FastAPI/ASGI layer — no endpoint business logic changes. Email delivery swaps the existing `httpx` SendGrid call for the Resend API endpoint; the `NotificationService._send_email` signature stays identical. slowapi uses a single `Limiter` with `get_tenant_key` as the default key function and per-route `key_func=get_remote_address` overrides on auth endpoints.

**Tech Stack:** FastAPI · Starlette · slowapi · httpx (existing) · Python 3.13 · pytest-asyncio · uv

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/core/config.py` | Modify | Add `resend_api_key`, `from_email`, `email_enabled` |
| `app/core/limiter.py` | Create | `get_tenant_key`, `limiter` singleton |
| `app/middleware/__init__.py` | Create | Package init (empty) |
| `app/middleware/request_id.py` | Create | Pure-ASGI `RequestIDMiddleware` |
| `app/api/exception_handlers.py` | Create | All FastAPI exception handler functions |
| `app/services/notification_service.py` | Modify | `_send_email` → Resend API endpoint |
| `app/jobs/retry_notifications.py` | Modify | `_retry_for_tenant` → Resend API endpoint |
| `app/api/v1/endpoints/auth.py` | Modify | Add `request: Request` param + `@limiter.limit` decorators |
| `app/main.py` | Modify | Register middleware, handlers, CORS, startup validation |
| `.env.example` | Modify | Add new env vars |
| `tests/unit/test_rate_limiting.py` | Create | Unit tests for `get_tenant_key` |
| `tests/unit/test_error_handlers.py` | Create | Unit tests for error envelope shape + request ID |
| `tests/integration/test_email_delivery.py` | Create | Mock httpx, verify Resend API call |

---

## Chunk 1: Settings + Email Delivery

### Task 1: Add production settings fields

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

**Codebase context:** `app/core/config.py` uses `pydantic_settings.BaseSettings` with `HABITARE_` prefix. `cors_origins: list[str]` already exists (line 42). Only add the three new email fields.

- [ ] **Step 1: Add fields to `app/core/config.py`**

After the `cors_origins` line, add:

```python
    # Email (Resend)
    resend_api_key: str = ""
    from_email: str = "noreply@habitare.app"
    email_enabled: bool = True
```

- [ ] **Step 2: Update `.env.example`**

Read the existing `.env.example` file first, then append these lines at the end:

```
# Email delivery (Resend — https://resend.com)
HABITARE_RESEND_API_KEY=re_your_key_here
HABITARE_FROM_EMAIL=noreply@yourdomain.com
HABITARE_EMAIL_ENABLED=true
```

- [ ] **Step 3: Verify settings load cleanly**

```bash
uv run python -c "from app.core.config import settings; print(settings.email_enabled, settings.resend_api_key)"
```

Expected: `True ` (empty string for key — no error)

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat(config): add resend email settings (resend_api_key, from_email, email_enabled)"
```

---

### Task 2: Swap email provider — Resend in NotificationService

**Files:**
- Modify: `app/services/notification_service.py` (lines 80–106)
- Modify: `app/jobs/retry_notifications.py`

**Codebase context:** `_send_email` in `notification_service.py` currently POSTs to SendGrid (`https://api.sendgrid.com/v3/mail/send`). The signature `(self, *, tenant_id, visit_id, host_id, host_email, visitor_name)` must not change — callers pass keyword args. The retry job at `app/jobs/retry_notifications.py` has its own inline SendGrid HTTP call (not calling NotificationService) that also needs swapping.

**Why `httpx.AsyncClient` not `resend` SDK:** The `resend` Python SDK is synchronous — calling it in an `async def` would block the event loop. Keeping `httpx.AsyncClient` and pointing it at Resend's REST API (`https://api.resend.com/emails`) is the correct async-safe approach.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_email_delivery.py
"""Integration test: email delivery via Resend API."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


@pytest.mark.asyncio
async def test_send_email_calls_resend_api(monkeypatch):
    """_send_email should POST to Resend API with correct shape."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "from_email", "noreply@test.com")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    posted_json = {}

    async def mock_post(url, **kwargs):
        posted_json.update(kwargs.get("json", {}))
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        import uuid
        from app.services.notification_service import NotificationService
        from unittest.mock import MagicMock as MM
        db = MM()
        db.add = MM()
        db.flush = AsyncMock()
        db.begin = MM()
        db.begin.return_value.__aenter__ = AsyncMock(return_value=db)
        db.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        svc = NotificationService(db)
        await svc._send_email(
            tenant_id=uuid.uuid4(),
            visit_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
            host_email="host@example.com",
            visitor_name="Alice",
        )
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://api.resend.com/emails"
        headers = call_args[1]["headers"]
        assert "Bearer re_test_key" in headers["Authorization"]
        body = call_args[1]["json"]
        assert body["to"] == ["host@example.com"]
        assert body["from"] == "noreply@test.com"


@pytest.mark.asyncio
async def test_send_email_skipped_when_disabled(monkeypatch):
    """_send_email should not make any HTTP call when email_enabled=False."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_enabled", False)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        import uuid
        from app.services.notification_service import NotificationService
        from unittest.mock import MagicMock as MM
        db = MM()
        db.add = MM()
        db.flush = AsyncMock()
        db.begin = MM()
        db.begin.return_value.__aenter__ = AsyncMock(return_value=db)
        db.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        svc = NotificationService(db)
        await svc._send_email(
            tenant_id=uuid.uuid4(),
            visit_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
            host_email="host@example.com",
            visitor_name="Alice",
        )
        mock_client.post.assert_not_called()
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/integration/test_email_delivery.py -v --tb=short
```

Expected: FAIL — `assert call_args[0][0] == "https://api.resend.com/emails"` (still using SendGrid URL)

- [ ] **Step 3: Swap `_send_email` in `notification_service.py`**

Replace the `try` block inside `_send_email` (lines 80–106) with:

```python
        try:
            if not settings.email_enabled:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.utcnow()
                await self.db.flush()
                return
            if not settings.resend_api_key:
                raise ValueError("HABITARE_RESEND_API_KEY not configured")
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                    json={
                        "from": settings.from_email,
                        "to": [host_email],
                        "subject": f"Visitor {visitor_name} has arrived",
                        "html": f"<p><strong>{visitor_name}</strong> has checked in.</p>",
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
        except Exception as exc:
            logger.warning("Email send failed for visit %s: %s", visit_id, exc)
            notification.status = NotificationStatus.FAILED

        await self.db.flush()
```

- [ ] **Step 4: Swap email call in `app/jobs/retry_notifications.py`**

Read the file. Find the `try` block inside `_retry_for_tenant` that posts to SendGrid. Replace the SendGrid URL and payload with Resend:

```python
                try:
                    if not getattr(settings, "resend_api_key", None):
                        raise ValueError("HABITARE_RESEND_API_KEY not configured")
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://api.resend.com/emails",
                            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                            json={
                                "from": getattr(settings, "from_email", "noreply@habitare.app"),
                                "to": [email_to],
                                "subject": f"Visitor {visitor_name} has arrived",
                                "html": f"<p><strong>{visitor_name}</strong> has checked in.</p>",
                            },
                            timeout=10.0,
                        )
                        resp.raise_for_status()
                    notif.status = NotificationStatus.SENT
                    notif.sent_at = datetime.utcnow()
                    logger.info("Retried notification %s: SENT", notif.id)
                except Exception as exc:
                    notif.retry_count += 1
                    logger.warning("Retry failed for notification %s (attempt %d): %s", notif.id, notif.retry_count, exc)
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/integration/test_email_delivery.py -v --tb=short
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add app/services/notification_service.py app/jobs/retry_notifications.py tests/integration/test_email_delivery.py
git commit -m "feat(email): swap SendGrid for Resend API; add email_enabled flag"
```

---

## Chunk 2: Rate Limiting

### Task 3: Create rate limiter module + unit tests

**Files:**
- Create: `app/core/limiter.py`
- Create: `tests/unit/test_rate_limiting.py`

**Codebase context:** `app/core/jwt.py` has `decode_token()` which raises `HTTPException` — the wrong contract for a rate-limit key function. Use `jwt.decode()` directly with `verify_signature=False` for the key function (we only need `tenant_id` for bucketing, not authentication). `app/core/config.py` has `settings.secret_key` and `settings.algorithm`. `slowapi` confirmed by Context7: single `Limiter` instance, `app.state.limiter = limiter`, per-route key override via `@limiter.limit("N/period", key_func=fn)`.

- [ ] **Step 1: Install slowapi**

```bash
uv add slowapi
```

Expected: `slowapi` added to `pyproject.toml` and `uv.lock`.

- [ ] **Step 2: Write failing unit tests**

```python
# tests/unit/test_rate_limiting.py
"""Unit tests for rate limiting key function."""
import uuid
import pytest
from unittest.mock import MagicMock, patch
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
```

- [ ] **Step 3: Run to confirm failure**

```bash
uv run pytest tests/unit/test_rate_limiting.py -v --tb=short
```

Expected: `ImportError: cannot import name 'get_tenant_key' from 'app.core.limiter'`

- [ ] **Step 4: Create `app/core/limiter.py`**

```python
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
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/unit/test_rate_limiting.py -v --tb=short
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add app/core/limiter.py tests/unit/test_rate_limiting.py pyproject.toml uv.lock
git commit -m "feat(limiter): add slowapi rate limiter with tenant-keyed key function"
```

---

### Task 4: Add rate limiting decorators to auth endpoints

**Files:**
- Modify: `app/api/v1/endpoints/auth.py`

**Codebase context:** Current `login`, `refresh`, `logout` handlers do NOT have `request: Request` in their signatures — slowapi requires it. The `@limiter.limit()` decorator must be placed BELOW `@router.post()` (closer to the function). Import `limiter` from `app.core.limiter`. Context7 confirmed: `@limiter.limit("5/minute", key_func=get_remote_address)` overrides the limiter's default key function for that route.

- [ ] **Step 1: Modify `app/api/v1/endpoints/auth.py`**

Add import at top:
```python
from fastapi import APIRouter, HTTPException, Request
from slowapi.util import get_remote_address
from app.core.limiter import limiter
```

Add `request: Request` parameter and `@limiter.limit` decorator to each auth endpoint:

```python
@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute", key_func=get_remote_address)
async def login(request: Request, body: LoginRequest, db: AsyncSessionDep) -> TokenResponse:
    ...  # body unchanged

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def refresh(request: Request, body: RefreshRequest, db: AsyncSessionDep) -> TokenResponse:
    ...  # body unchanged

@router.post("/logout")
@limiter.limit("20/minute", key_func=get_remote_address)
async def logout(request: Request, body: LogoutRequest, db: AsyncSessionDep):
    ...  # body unchanged
```

**Important:** `request: Request` must be the FIRST parameter after `self` (if any). The rest of the handler body is unchanged.

- [ ] **Step 2: Verify app imports cleanly**

```bash
uv run python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/endpoints/auth.py
git commit -m "feat(auth): add slowapi rate limiting to login/refresh/logout endpoints"
```

---

## Chunk 3: Middleware + Error Handlers + main.py Wiring

### Task 5: Pure ASGI RequestID middleware

**Files:**
- Create: `app/middleware/__init__.py`
- Create: `app/middleware/request_id.py`

**Codebase context:** Context7 confirmed the pure ASGI middleware pattern for Starlette: `Request(scope)` to access `request.state`, `MutableHeaders(scope=message)` to add response headers. Pure ASGI avoids the `BaseHTTPMiddleware` streaming/exception-handler interaction bugs. `SlowAPIASGIMiddleware` must also be pure ASGI — middleware registration order in `main.py` matters (`RequestIDMiddleware` outermost so request_id is set before rate limiter fires).

- [ ] **Step 1: Create `app/middleware/__init__.py`**

Empty file.

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_error_handlers.py
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
```

- [ ] **Step 3: Run to confirm failure**

```bash
uv run pytest tests/unit/test_error_handlers.py -v --tb=short
```

Expected: FAIL — responses return old `{"detail": "..."}` shape, no `x-request-id` header.

- [ ] **Step 4: Create `app/middleware/request_id.py`**

```python
"""Pure ASGI middleware: inject X-Request-ID into every response.

Uses pure ASGI (not BaseHTTPMiddleware) to avoid streaming response
and exception handler interaction issues in Starlette.

Context7 confirmed patterns:
- Request(scope) to access request.state
- MutableHeaders(scope=message) to inject response headers
- scope["type"] check to pass through non-HTTP (WebSocket, lifespan)
"""
import uuid
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Store on request.state so exception handlers can read it
        request.state.request_id = request_id

        async def send_with_request_id(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        await self.app(scope, receive, send_with_request_id)
```

- [ ] **Step 5: Commit middleware (tests still fail — wired in Task 7)**

```bash
git add app/middleware/__init__.py app/middleware/request_id.py
git commit -m "feat(middleware): add pure ASGI RequestIDMiddleware"
```

---

### Task 6: Exception handlers module

**Files:**
- Create: `app/api/exception_handlers.py`

**Codebase context:** Handlers are defined here and registered in `main.py`. Context7 confirmed: register on `StarletteHTTPException` (from `starlette.exceptions`) to catch routing-level 404/405 in addition to app-raised `HTTPException`. `getattr(request.state, "request_id", None)` is safe even before `RequestIDMiddleware` runs (early errors).

- [ ] **Step 1: Create `app/api/exception_handlers.py`**

```python
"""FastAPI exception handlers — structured error envelope for all error paths.

All handlers return:
    {"error": {"code": str, "message": str, "detail": any, "request_id": str | None}}

Registered in app/main.py on StarletteHTTPException (not fastapi.HTTPException)
so routing-level 404/405 errors also use the envelope.
"""
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {
            "code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "detail": None,
            "request_id": _request_id(request),
        }},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid request body",
            "detail": exc.errors(),
            "request_id": _request_id(request),
        }},
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please try again later.",
            "detail": None,
            "request_id": _request_id(request),
        }},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "detail": None,
            "request_id": _request_id(request),
        }},
    )
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from app.api.exception_handlers import http_exception_handler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/exception_handlers.py
git commit -m "feat(errors): add structured error envelope exception handlers"
```

---

### Task 7: Wire everything in main.py + fix CORS

**Files:**
- Modify: `app/main.py`

**Codebase context:** Current `main.py` hardcodes `["http://localhost:3000"]` in `CORSMiddleware`. `settings.cors_origins` already exists in `config.py`. Middleware registration order matters: `RequestIDMiddleware` must be registered LAST (so it wraps everything and runs first on each request). `SlowAPIASGIMiddleware` inside it. `CORSMiddleware` innermost. Startup validation raises `RuntimeError` if `email_enabled=True` but `resend_api_key` is empty.

- [ ] **Step 1: Rewrite `app/main.py`**

```python
"""
Habitare - QR-Based Visitor Management System
FastAPI Application Entry Point
"""
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.exception_handlers import (
    http_exception_handler,
    rate_limit_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.limiter import limiter
from app.middleware.request_id import RequestIDMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Habitare API",
    description="QR-Based Visitor Management System",
    version="0.1.0",
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter

# ── Exception handlers ────────────────────────────────────────────────────────
# StarletteHTTPException (not fastapi.HTTPException) catches routing 404/405 too
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── Middleware (outermost registered last — runs first on request) ─────────────
# Order: RequestID → SlowAPI → CORS → route handler
app.add_middleware(CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(SlowAPIASGIMiddleware)
app.add_middleware(RequestIDMiddleware)

# ── Startup validation ────────────────────────────────────────────────────────
@app.on_event("startup")
async def validate_config() -> None:
    if settings.email_enabled and not settings.resend_api_key:
        raise RuntimeError(
            "HABITARE_RESEND_API_KEY must be set when HABITARE_EMAIL_ENABLED=true. "
            "Get a free API key at https://resend.com"
        )
    logger.info(
        "Habitare API starting — email_enabled=%s, environment=%s",
        settings.email_enabled,
        settings.environment,
    )

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.visitors import router as visitors_router
from app.api.v1.endpoints.visits import router as visits_router
from app.api.v1.endpoints.invitations import router as invitations_router
from app.api.v1.endpoints.qr import router as qr_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.admin import router as admin_router

API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(visitors_router, prefix=API_PREFIX)
app.include_router(visits_router, prefix=API_PREFIX)
app.include_router(invitations_router, prefix=API_PREFIX)
app.include_router(qr_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Habitare API is running", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "habitare-api", "version": "0.1.0"}
```

- [ ] **Step 2: Run error handler + request ID tests**

```bash
uv run pytest tests/unit/test_error_handlers.py -v --tb=short
```

Expected: `5 passed`

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -q --tb=short 2>&1 | tail -15
```

Expected: same passing count as before Phase 5 work + new tests passing; 0 new failures.

- [ ] **Step 4: Verify startup validation works**

```bash
HABITARE_EMAIL_ENABLED=true HABITARE_RESEND_API_KEY="" uv run python -c "
import asyncio
from app.main import app, validate_config
try:
    asyncio.run(validate_config())
    print('ERROR: should have raised')
except RuntimeError as e:
    print('OK — raises RuntimeError:', str(e)[:60])
"
```

Expected: `OK — raises RuntimeError: HABITARE_RESEND_API_KEY must be set...`

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "feat(main): wire rate limiter, error handlers, RequestIDMiddleware, configurable CORS"
```

---

## Chunk 4: Final Verification + PR

### Task 8: Full test suite + push + PR

**Files:** None — verification only.

- [ ] **Step 1: Run complete test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -25
```

Expected: all Phase 5 tests pass + no regressions. Pre-existing failures (test_prereg_flow, test_visitor_flow, test_vms_rls) may still fail — these are pre-Phase-5 known failures, not regressions.

- [ ] **Step 2: Verify OpenAPI still works**

```bash
uv run python -c "from app.main import app; import json; routes = [r.path for r in app.routes]; print(f'Routes: {len(routes)}'); print(routes[:5])"
```

Expected: 30+ routes listed cleanly.

- [ ] **Step 3: Smoke test email disabled path (no API key needed)**

In `.env`, temporarily set `HABITARE_EMAIL_ENABLED=false`, then:

```bash
uv run python -c "
import asyncio
from app.main import validate_config
asyncio.run(validate_config())
print('OK — starts fine with email_enabled=False')
"
```

Expected: `OK — starts fine with email_enabled=False`

Reset `.env` to original value after.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/phase-5-production-hardening
```

- [ ] **Step 5: Create PR**

```bash
/opt/homebrew/bin/gh pr create \
  --title "feat(phase-5): production hardening — email, rate limiting, error envelope, request ID" \
  --body "$(cat <<'EOF'
## Summary

- **Email**: Swap SendGrid for Resend API via httpx (async-safe); `email_enabled` flag for test environments; startup validation if key missing
- **Rate limiting**: slowapi with `SlowAPIASGIMiddleware`; tenant-keyed by default; IP-keyed on auth endpoints (5/min login, 10/min refresh, 20/min logout)
- **Error envelope**: Consistent \`{\"error\": {\"code\", \"message\", \"detail\", \"request_id\"}}\` on all paths including routing 404/405 via \`StarletteHTTPException\`
- **Request ID**: Pure ASGI middleware; echoes client \`X-Request-ID\` or generates UUID; exposed in CORS headers
- **CORS**: Wired to \`settings.cors_origins\` (was hardcoded to localhost); \`X-Request-ID\` in \`expose_headers\`

## Test Plan
- [ ] `uv run pytest tests/unit/test_rate_limiting.py tests/unit/test_error_handlers.py -v`
- [ ] `uv run pytest tests/integration/test_email_delivery.py -v`
- [ ] `uv run pytest tests/ -q` — 0 new failures
- [ ] Set `HABITARE_EMAIL_ENABLED=true HABITARE_RESEND_API_KEY=""` → app refuses to start
- [ ] `curl -X POST /api/v1/auth/login` 6 times in 1 minute → 6th returns 429 with error envelope
- [ ] Unknown route → 404 with `{"error": {"code": "HTTP_404", ...}}`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Implementation Notes

### Middleware registration order in FastAPI

`app.add_middleware()` prepends to the middleware stack — the LAST `add_middleware` call wraps everything and runs FIRST on incoming requests. The order in `main.py` (CORS → SlowAPI → RequestID) results in: RequestID runs first (sets request_id), then SlowAPI (can read request_id for error responses), then CORS.

### slowapi requires `request: Request` parameter

Every route decorated with `@limiter.limit()` MUST have `request: Request` as a parameter. FastAPI will still inject it from the ASGI scope — it doesn't need to be in the OpenAPI schema as a user-supplied input. Place `request: Request` as the first parameter.

### Why `StarletteHTTPException` and not `fastapi.HTTPException`

FastAPI's `HTTPException` is a subclass of Starlette's `HTTPException`. Routing-level errors (unknown paths, wrong HTTP method) raise Starlette's version directly — not FastAPI's subclass. Registering the handler on `StarletteHTTPException` catches both. Confirmed by Context7 FastAPI docs.

### email_enabled in tests

All existing integration tests use a real DB but mock email. With `email_enabled` defaulting to `True` in settings, tests that trigger check-ins would try to send email. Set `HABITARE_EMAIL_ENABLED=false` in `.env.test` or use `monkeypatch.setattr(settings, "email_enabled", False)` in fixtures that trigger email paths.
