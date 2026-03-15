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

- **Email delivery** — Replace raw SendGrid `httpx` call with the `resend` Python SDK; add `email_enabled` flag to skip sends in test environments
- **Rate limiting** — `slowapi` guards on auth endpoints (per IP) and all other routes (per tenant); in-memory store (single server)
- **Structured error responses** — Consistent `{"error": {"code", "message", "detail", "request_id"}}` envelope across all error paths; catch-all 500 handler suppresses tracebacks
- **Request ID middleware** — `X-Request-ID` on every response; echoes client-supplied value or generates UUID
- **Configurable CORS** — `HABITARE_CORS_ORIGINS` setting replaces hardcoded `localhost:3000`; `X-Request-ID` added to exposed headers

### Out of scope

- Sentry, structlog, Prometheus — Phase 6 (alongside deployment)
- Per-tier rate limits (basic/pro/enterprise) — Phase 6 (requires billing flow)
- Cloudflare Tunnel, launchd services, production Docker Compose — Phase 6
- Email templates (HTML) — Phase 6

---

## Architecture

### Email Delivery (Resend)

The `NotificationService._send_email()` method is the single point of email dispatch — used by the visit check-in flow (immediate send via `BackgroundTasks`) and the ARQ retry job (`retry_failed_notifications`). Only this method changes; all callers remain untouched.

```python
# app/services/notification.py
import resend

async def _send_email(self, to: str, subject: str, html: str) -> None:
    if not settings.email_enabled:
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send({
        "from": settings.from_email,
        "to": to,
        "subject": subject,
        "html": html,
    })
```

`email_enabled = False` in the test environment prevents any real sends during CI. The `resend` SDK raises on HTTP errors — the existing `try/except` in `_send_email` catches these and increments `retry_count`, keeping the retry loop intact.

### Rate Limiting (slowapi)

Two limiters — one keyed by IP (for unauthenticated auth routes), one keyed by `tenant_id` extracted from the JWT (for authenticated routes).

```python
# app/core/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_tenant_key(request: Request) -> str:
    """Extract tenant_id from JWT for authed routes; fall back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = decode_token(auth.removeprefix("Bearer "))
            return payload.get("tenant_id", get_remote_address(request))
        except Exception:
            pass
    return get_remote_address(request)

ip_limiter = Limiter(key_func=get_remote_address)
tenant_limiter = Limiter(key_func=get_tenant_key)
```

**Limits by endpoint group:**

| Group | Limit | Key |
|---|---|---|
| `POST /auth/login` | 5/minute | IP |
| `POST /auth/refresh` | 10/minute | IP |
| `POST /auth/logout` | 20/minute | IP |
| All other `POST`/`PUT`/`DELETE` | 60/minute | tenant_id |
| All `GET` (authenticated) | 200/minute | tenant_id |

Rate limit violations return `429 Too Many Requests` using the standard error envelope.

`slowapi` uses in-memory storage — limits reset on process restart. Appropriate for a single Mac Mini server. Cloudflare's rate limiting (Phase 6) adds a second layer before traffic reaches the app.

### Structured Error Responses

All error responses share one envelope shape:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests",
    "detail": null,
    "request_id": "a3f8c2d1-4e5b-..."
  }
}
```

**Exception handlers registered in `app/main.py`:**

| Exception type | Status | `code` |
|---|---|---|
| `HTTPException` | `exc.status_code` | `HTTP_<status>` |
| `RequestValidationError` | 422 | `VALIDATION_ERROR` |
| `RateLimitExceeded` | 429 | `RATE_LIMIT_EXCEEDED` |
| `Exception` (catch-all) | 500 | `INTERNAL_ERROR` |

The catch-all handler logs the full traceback server-side but returns only `INTERNAL_ERROR` to the client — no stack traces exposed in production.

### Request ID Middleware

```python
# app/middleware/request_id.py
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

`request.state.request_id` is available to exception handlers so the same ID appears in both the response header and the error envelope body.

### Configurable CORS

```python
# app/core/config.py
cors_origins: list[str] = ["http://localhost:3000"]
```

Parsed from `HABITARE_CORS_ORIGINS` env var (JSON array string). `X-Request-ID` added to `expose_headers` so frontend code can read it from error responses.

---

## Files

| File | Change |
|---|---|
| `app/core/config.py` | Add `resend_api_key`, `from_email`, `email_enabled`, `cors_origins` |
| `app/core/limiter.py` | Create — `ip_limiter`, `tenant_limiter`, `get_tenant_key` |
| `app/middleware/__init__.py` | Create — package init |
| `app/middleware/request_id.py` | Create — `RequestIDMiddleware` |
| `app/services/notification.py` | Modify `_send_email()` — swap SendGrid for Resend SDK |
| `app/main.py` | Register middleware, exception handlers, rate limiters; update CORS |
| `.env.example` | Add new env vars |
| `tests/unit/test_rate_limiting.py` | Unit tests for limiter key functions |
| `tests/unit/test_error_handlers.py` | Unit tests for exception handler shapes |
| `tests/integration/test_email_delivery.py` | Integration test — mocked Resend send |

---

## Settings additions

```python
# app/core/config.py additions
resend_api_key: str = ""              # HABITARE_RESEND_API_KEY
from_email: str = "noreply@habitare.app"  # HABITARE_FROM_EMAIL
email_enabled: bool = True            # HABITARE_EMAIL_ENABLED (set False in tests)
cors_origins: list[str] = ["http://localhost:3000"]  # HABITARE_CORS_ORIGINS
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

All existing `HTTPException` raises remain unchanged — the exception handler wraps them in the envelope automatically. No endpoint code changes needed.

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
{"detail": [{"loc": ["body", "email"], "msg": "value is not a valid email", "type": "value_error.email"}]}
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
- `get_tenant_key` returns `tenant_id` when valid JWT present
- `get_tenant_key` falls back to IP when no Authorization header
- `get_tenant_key` falls back to IP when JWT is invalid/expired

### Unit — `tests/unit/test_error_handlers.py`
- `HTTPException(403)` → envelope with `code="HTTP_403"`, `status=403`
- `RequestValidationError` → envelope with `code="VALIDATION_ERROR"`, `status=422`
- Unhandled `Exception` → envelope with `code="INTERNAL_ERROR"`, `status=500`, no traceback in body
- All responses include `X-Request-ID` header

### Integration — `tests/integration/test_email_delivery.py`
- Mock `resend.Emails.send` — verify called with correct `to`, `from`, `subject`
- `email_enabled=False` → `resend.Emails.send` never called
- Notification with missing `to` in payload → skipped gracefully

### Integration — `tests/integration/test_rate_limiting.py`
- `POST /auth/login` 6th attempt in 1 minute → 429 with error envelope
- Authenticated `POST` 61st attempt → 429

---

## Security Decisions

| Decision | Choice | Reason |
|---|---|---|
| Rate limit storage | In-memory (slowapi default) | Single Mac Mini server; Redis adds complexity with no benefit at this scale |
| Rate limit key for auth | IP address | No JWT exists yet at login time |
| Rate limit key for authed routes | `tenant_id` | Prevents one tenant's traffic from affecting another |
| Email provider | Resend | Simpler API than SendGrid, better free tier, Cloudflare DNS integration in Phase 6 |
| Traceback exposure | Suppressed in response | Logged server-side; never sent to client |
| CORS wildcard | Not used | Explicit origin list even for development |
