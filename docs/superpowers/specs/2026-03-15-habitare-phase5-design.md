# Habitare — Phase 5 Design Spec

**Date:** 2026-03-15
**Project:** Habitare QR-Based Visitor Management System
**Phase:** 5 — Production Readiness (App-Level Hardening)
**Stack:** FastAPI · PostgreSQL 17 (RLS) · SQLAlchemy 2.0 async · Python 3.13 · slowapi · Resend

---

## Goal

Harden the application for production deployment by fixing four gaps: email delivery (currently broken), rate limiting (auth endpoints are brute-forceable), structured error responses (500s expose tracebacks), and configurable CORS (hardcoded to localhost). Phase 6 will add Mac Mini + Cloudflare Tunnel deployment on top of this hardened foundation.

---

## Scope

### In scope

- **Email delivery** — Replace raw SendGrid `httpx` call with Resend's API via `httpx.AsyncClient` (keeps async-safe pattern); add `email_enabled` flag to skip sends in test environments; set `resend_api_key` once at startup
- **Rate limiting** — Single `slowapi` limiter with per-route key function overrides; `SlowAPIASGIMiddleware` (avoids `BaseHTTPMiddleware` streaming issues); auth endpoints keyed by IP, authenticated routes by `tenant_id`
- **Structured error responses** — Consistent `{"error": {"code", "message", "detail", "request_id"}}` envelope; handlers registered on `StarletteHTTPException` (catches routing-level 404/405 too); catch-all 500 suppresses tracebacks
- **Request ID middleware** — Pure ASGI middleware (not `BaseHTTPMiddleware`) adds `X-Request-ID` to every response; echoes client-supplied value or generates UUID
- **Configurable CORS** — Update existing `cors_origins` setting wiring in `main.py` (field already exists in `config.py`); add `X-Request-ID` to exposed headers

### Out of scope

- Sentry, structlog, Prometheus — Phase 6 (alongside deployment)
- Per-tier rate limits (basic/pro/enterprise) — Phase 6 (requires billing flow)
- Cloudflare Tunnel, launchd services, production Docker Compose — Phase 6
- Email HTML templates — Phase 6

---

## Architecture

### Email Delivery (Resend)

The current `_send_email` in `NotificationService` makes an `httpx.AsyncClient` POST to SendGrid. We keep the same async pattern but swap the endpoint, headers, and body to Resend's API. This avoids the sync-blocking problem that would occur with the `resend` Python SDK (which is synchronous and would block the event loop if called directly in an async function).

`resend_api_key` is set once at application startup in `app/main.py` (or a lifespan event) — not on every call, which would be a global mutation race condition.

```python
# app/services/notification.py — only the inner _send_email implementation changes
# The method signature and all callers remain identical.

async def _send_email(self, *, to: str, subject: str, html: str) -> None:
    """Send email via Resend API using httpx (async-safe)."""
    if not settings.email_enabled:
        return
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.from_email,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
```

**Note:** The existing `try/except` in the calling code catches `httpx.HTTPError` — this remains intact. On failure, `retry_count` is incremented and the ARQ retry job handles recovery.

**Startup wiring** — add to `app/main.py` (or lifespan):
```python
# Validate email config at startup, not per-request
if settings.email_enabled and not settings.resend_api_key:
    raise RuntimeError("HABITARE_RESEND_API_KEY must be set when email_enabled=True")
```

### Rate Limiting (slowapi)

**Single limiter** with `get_tenant_key` as the default key function. Auth endpoints override with `key_func=get_remote_address` at the decorator level — this is the idiomatic slowapi pattern and avoids the `app.state.limiter` confusion of registering two separate limiters.

```python
# app/core/limiter.py
import jwt as pyjwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

def get_tenant_key(request: Request) -> str:
    """Extract tenant_id from JWT for authed routes; fall back to IP.

    Uses raw jwt.decode() — NOT decode_token() from app/core/jwt.py.
    decode_token() raises HTTPException (wrong contract for a key function).
    Raw decode with verify=False is safe here because we only need the
    tenant_id claim for rate limiting, not for authentication.
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
                return tenant_id
        except Exception:
            pass
    return get_remote_address(request)

limiter = Limiter(key_func=get_tenant_key)
```

**Registration in `main.py`:**
```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware  # NOT SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)  # pure ASGI — no BaseHTTPMiddleware
```

**Note:** `SlowAPIASGIMiddleware` is used instead of `SlowAPIMiddleware`. The ASGI variant avoids the `BaseHTTPMiddleware` streaming response and exception handler interaction issues present in newer FastAPI/Starlette versions.

**Limits by endpoint:**

| Endpoint | Limit | Key override |
|---|---|---|
| `POST /auth/login` | 5/minute | `key_func=get_remote_address` |
| `POST /auth/refresh` | 10/minute | `key_func=get_remote_address` |
| `POST /auth/logout` | 20/minute | `key_func=get_remote_address` |
| All other `POST`/`PUT`/`DELETE` | 60/minute | default (`tenant_id`) |
| All `GET` (authenticated) | 200/minute | default (`tenant_id`) |

Rate limit violations return `429 Too Many Requests` using the standard error envelope (see below). `_rate_limit_exceeded_handler` is replaced by a custom handler that wraps the response in the error envelope.

### Structured Error Responses

All error responses share one envelope shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request body",
    "detail": [{"loc": ["body", "email"], "msg": "value is not a valid email"}],
    "request_id": "a3f8c2d1-4e5b-..."
  }
}
```

**Critical:** Handlers are registered on `StarletteHTTPException` (from `starlette.exceptions`), not `fastapi.HTTPException`. This ensures routing-level errors (404 Not Found for unknown routes, 405 Method Not Allowed) also return the envelope shape — not Starlette's default `{"detail": "..."}`.

```python
# app/main.py
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {
            "code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "detail": None,
            "request_id": getattr(request.state, "request_id", None),
        }},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid request body",
            "detail": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        }},
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests",
            "detail": None,
            "request_id": getattr(request.state, "request_id", None),
        }},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("habitare").exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "detail": None,
            "request_id": getattr(request.state, "request_id", None),
        }},
    )
```

`getattr(request.state, "request_id", None)` is safe even if the middleware hasn't run (e.g., very early errors).

### Request ID Middleware (Pure ASGI)

Pure ASGI middleware — no `BaseHTTPMiddleware` — avoids the exception handler interaction issues and streaming response buffering:

```python
# app/middleware/request_id.py
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send

class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id  # accessible as request.state.request_id in handlers

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        await self.app(scope, receive, send_with_header)
```

Registration order in `main.py` matters — `RequestIDMiddleware` must be added **before** `SlowAPIASGIMiddleware` so `request_id` is set when exception handlers run:
```python
app.add_middleware(RequestIDMiddleware)   # outermost — runs first on request
app.add_middleware(SlowAPIASGIMiddleware) # inner
```

### Configurable CORS

`cors_origins: list[str]` already exists in `app/core/config.py`. The change is in `app/main.py` — replace the hardcoded list with `settings.cors_origins` and add `X-Request-ID` to `expose_headers`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # was: ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],       # new: frontend can read request ID
)
```

---

## Files

| File | Change |
|---|---|
| `pyproject.toml` | Add `resend` (unused, kept for future SDK), `slowapi` via `uv add slowapi` |
| `app/core/config.py` | Add `resend_api_key`, `from_email`, `email_enabled`; `cors_origins` already exists |
| `app/core/limiter.py` | Create — `limiter`, `get_tenant_key` |
| `app/middleware/__init__.py` | Create — package init (empty) |
| `app/middleware/request_id.py` | Create — pure ASGI `RequestIDMiddleware` |
| `app/services/notification.py` | Modify `_send_email()` — swap SendGrid endpoint for Resend API |
| `app/main.py` | Register middleware (correct order), exception handlers, CORS update, startup validation |
| `.env.example` | Add `HABITARE_RESEND_API_KEY`, `HABITARE_FROM_EMAIL`, `HABITARE_EMAIL_ENABLED` |
| `tests/unit/test_rate_limiting.py` | Unit tests for `get_tenant_key` |
| `tests/unit/test_error_handlers.py` | Unit tests for exception handler shapes + request ID |
| `tests/integration/test_email_delivery.py` | Integration test — mock httpx, verify Resend API call shape |

---

## Settings additions

```python
# app/core/config.py — new fields only (cors_origins already exists)
resend_api_key: str = ""                       # HABITARE_RESEND_API_KEY
from_email: str = "noreply@habitare.app"       # HABITARE_FROM_EMAIL
email_enabled: bool = True                     # HABITARE_EMAIL_ENABLED
# cors_origins: list[str] already present — no change needed
```

`.env.example` additions:
```
HABITARE_RESEND_API_KEY=re_...
HABITARE_FROM_EMAIL=noreply@yourdomain.com
HABITARE_EMAIL_ENABLED=true
HABITARE_CORS_ORIGINS=["http://localhost:3000"]
```

---

## Error Response Format

All existing `HTTPException` raises remain unchanged — the exception handler wraps them automatically. No endpoint code changes needed.

**Before (current):**
```json
{"detail": "Insufficient permissions"}
```

**After:**
```json
{
  "error": {
    "code": "HTTP_403",
    "message": "Insufficient permissions",
    "detail": null,
    "request_id": "a3f8c2d1-..."
  }
}
```

**Validation error (before):**
```json
{"detail": [{"loc": ["body", "email"], "msg": "value is not a valid email"}]}
```

**After:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request body",
    "detail": [{"loc": ["body", "email"], "msg": "value is not a valid email"}],
    "request_id": "b4c9d3e2-..."
  }
}
```

---

## Testing

### Unit — `tests/unit/test_rate_limiting.py`
- `get_tenant_key` returns `tenant_id` when valid JWT present (uses `verify_signature=False`)
- `get_tenant_key` falls back to IP when no `Authorization` header
- `get_tenant_key` falls back to IP when JWT is malformed
- `get_tenant_key` falls back to IP when JWT has no `tenant_id` claim

### Unit — `tests/unit/test_error_handlers.py`
- `HTTPException(403)` → envelope with `code="HTTP_403"`, `status=403`, `request_id` present
- Unknown route → `StarletteHTTPException(404)` → envelope (not raw `{"detail": "Not Found"}`)
- `RequestValidationError` → `code="VALIDATION_ERROR"`, `status=422`, `detail` contains error list
- Unhandled `Exception` → `code="INTERNAL_ERROR"`, `status=500`, no traceback in `detail`
- Client-supplied `X-Request-ID: my-id` → response header `X-Request-ID: my-id` (echoed, not overwritten)
- No client `X-Request-ID` → response header contains generated UUID

### Integration — `tests/integration/test_email_delivery.py`
- Mock `httpx.AsyncClient.post` — verify called with Resend URL, correct auth header, correct body shape (`from`, `to`, `subject`, `html`)
- `email_enabled=False` → `httpx.AsyncClient.post` never called
- Notification with missing `to` in payload → skipped gracefully, no exception

---

## Security Decisions

| Decision | Choice | Reason |
|---|---|---|
| Email HTTP client | `httpx.AsyncClient` (kept) | Resend SDK is sync — would block event loop; keeping httpx maintains async-safe pattern |
| `resend_api_key` initialization | Once at startup | Per-call global mutation is not thread-safe under async concurrency |
| Rate limit storage | In-memory (slowapi default) | Single Mac Mini server; Redis adds complexity with no benefit at this scale |
| Rate limit key for auth | IP address | No JWT exists yet at login time |
| Rate limit key for authed routes | `tenant_id` | Prevents one tenant's traffic from affecting another |
| JWT decode in key function | `verify_signature=False` | Key function only needs `tenant_id` claim for bucketing, not authentication |
| Middleware pattern | Pure ASGI (not `BaseHTTPMiddleware`) | Avoids streaming/exception handler interaction bugs in Starlette |
| ASGI rate limit middleware | `SlowAPIASGIMiddleware` | ASGI variant preferred over `SlowAPIMiddleware` for same reason |
| HTTP exception handler target | `StarletteHTTPException` | Catches routing-level 404/405 in addition to app-raised `HTTPException` |
| Traceback exposure | Suppressed in response | Logged server-side; never sent to client |
| CORS wildcard | Not used | Explicit origin list even for development |
