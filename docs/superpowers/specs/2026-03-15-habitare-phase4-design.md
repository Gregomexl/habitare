# Habitare — Phase 4 Design Spec

**Date:** 2026-03-15
**Project:** Habitare QR-Based Visitor Management System
**Phase:** 4 — RBAC, User Management & Background Jobs
**Stack:** FastAPI · PostgreSQL 17 (RLS) · SQLAlchemy 2.0 async · Python 3.13 · ARQ · Redis 7

---

## Goal

Two independent subsystems delivered in sequence:

1. **RBAC + User Management** — add a `require_role()` dependency guard, implement user management endpoints for `PROPERTY_ADMIN`, and complete the `SUPER_ADMIN` admin endpoints.
2. **Background Jobs** — ARQ + Redis worker for email notification retry and expired refresh token cleanup.

---

## Scope

### Sub-spec A: RBAC + User Management

**In scope:**
- `require_role(*roles)` dependency factory in `app/api/deps.py`
- Guard `/admin/*` with `SUPER_ADMIN`, user management endpoints with `PROPERTY_ADMIN+`
- `PUT /users/me` — update own profile (any authenticated user)
- `GET /users/` [PROPERTY_ADMIN+] — list tenant users
- `POST /users/` [PROPERTY_ADMIN+] — create staff account, return temp password once
- `PUT /users/{id}` [PROPERTY_ADMIN+] — update user (deactivate, profile fields, role within bounds)
- `POST /admin/tenants/` [SUPER_ADMIN] — create tenant
- `PUT /admin/tenants/{id}` [SUPER_ADMIN] — update tenant
- New Pydantic schemas: `UserUpdateMe`, `UserCreate`, `UserCreateResponse`, `UserUpdate`, `TenantCreate`, `TenantUpdate`

**Out of scope:**
- Implicit role hierarchy (SUPER_ADMIN must be listed explicitly where PROPERTY_ADMIN is allowed)
- Email invitation flow for new users (temp password returned in response, shared out-of-band)
- SUPER_ADMIN creation via API (seeded via migrations only)
- Social login, 2FA, SSO
- Rate limiting

### Sub-spec B: Background Jobs

**In scope:**
- ARQ worker entry point: `app/worker.py`
- `retry_failed_notifications` cron job (every 5 minutes)
- `cleanup_expired_tokens` cron job (nightly 03:00 UTC)
- `notifications.retry_count` column + migration

**Out of scope:**
- Invitation expiry auto-transition (enforced at query time already)
- New email providers (SendGrid path unchanged)
- Job monitoring dashboard

---

## Architecture

### RBAC

**Pattern:** Dependency factory — `require_role(*roles)` returns a FastAPI `Depends()` that reads `current_user.role` from the existing `CurrentUserDep` and raises `403 Forbidden` if the role is not in the allowed set. No implicit hierarchy — each guard lists every role explicitly. Keeps authorization auditable.

```python
def require_role(*roles: UserRole):
    async def check(current_user: CurrentUserDep) -> TokenData:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return Depends(check)
```

`RequireAdmin = require_role(UserRole.PROPERTY_ADMIN, UserRole.SUPER_ADMIN)`
`RequireSuperAdmin = require_role(UserRole.SUPER_ADMIN)`

All existing endpoints remain unchanged — they are `TENANT_USER`-accessible, which is correct. RLS already handles tenant isolation.

**Admin endpoints and RLS:** Admin endpoints operate on the `tenants` table which has no RLS policy. Admin endpoint handlers do **not** call `set_rls()` — they query cross-tenant by design. This is an intentional exception to the pattern used everywhere else.

### User Management

**Temp password flow:** `secrets.token_urlsafe(12)` generates a 16-character URL-safe string. Hashed with Argon2id before storage. Returned plaintext **once** in `UserCreateResponse.temp_password`. No email sent — caller shares out-of-band.

**Role constraint:** `POST /users/` and `PUT /users/{id}` validate that `role != SUPER_ADMIN`. A `PROPERTY_ADMIN` cannot escalate a user to `SUPER_ADMIN`. Validated at the endpoint level (not the schema) to allow clear error messaging.

**Self-edit constraint:** `PUT /users/{id}` where `id == current_user.user_id` returns 400 — use `PUT /users/me` instead. This prevents accidental self-deactivation. Admin-on-admin edits (a `PROPERTY_ADMIN` editing another `PROPERTY_ADMIN`) are permitted — the caller is assumed to be managing their own tenant staff.

**RLS:** All user management endpoints operate within the caller's tenant. `set_rls(db, current_user.tenant_id)` is called before any query — RLS ensures `PUT /users/{id}` automatically returns 404 for users in other tenants.

### Background Jobs (ARQ)

**Worker:** `app/worker.py` defines `WorkerSettings` with two cron jobs and a Redis pool from `settings.redis_url`. Run with: `uv run arq app.worker.WorkerSettings`.

**`retry_failed_notifications`:** Queries `notifications WHERE status = 'FAILED' AND retry_count < 3 AND created_at > now() - interval '24 hours'` **grouped by `tenant_id`**. For each tenant group the job calls `SET LOCAL app.current_tenant_id` before processing that group's notifications — this satisfies RLS on the `notifications` table. Each notification re-calls `NotificationService.send_email()`. On success: `status = SENT`, `sent_at = now()`. On failure: `retry_count += 1`, `status = FAILED`. The 24-hour window prevents retrying stale failures indefinitely.

**Worker DB session and RLS:** The ARQ worker creates its own `AsyncSession` via `async_session()`. Because `notifications` is RLS-gated by `tenant_id`, the job groups failed notifications by `tenant_id` and sets `SET LOCAL app.current_tenant_id = '<tid>'` within each transaction before querying. This avoids requiring a superuser role for the worker and keeps the existing `habitare_app` non-superuser DB role.

**`cleanup_expired_tokens`:** Deletes `refresh_tokens WHERE expires_at < now() - interval '30 days' OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days')`. Logs deleted row count. No application-layer pagination needed — DELETE with a WHERE clause is atomic.

**Fast path unchanged:** `BackgroundTasks` in the visit check-in flow still fires email immediately. ARQ handles recovery only.

---

## Files

### Sub-spec A: New / Modified

| File | Change |
|------|--------|
| `app/api/deps.py` | Add `require_role()`, `RequireAdmin`, `RequireSuperAdmin` |
| `app/schemas/user.py` | Add `UserUpdateMe`, `UserCreate`, `UserCreateResponse`, `UserUpdate` |
| `app/schemas/tenant.py` | Add `TenantCreate`, `TenantUpdate` |
| `app/api/v1/endpoints/users.py` | Add `PUT /users/me`, `GET /users/`, `POST /users/`, `PUT /users/{id}` |
| `app/api/v1/endpoints/admin.py` | Add role guards, implement `POST /admin/tenants/`, `PUT /admin/tenants/{id}` |
| `tests/unit/test_require_role.py` | Unit tests for `require_role()` |
| `tests/integration/test_user_management.py` | Integration tests for user management flows |
| `tests/integration/test_admin_endpoints.py` | Integration tests for admin endpoints |

### Sub-spec B: New / Modified

| File | Change |
|------|--------|
| `app/worker.py` | ARQ `WorkerSettings`, cron job registration |
| `app/jobs/retry_notifications.py` | `retry_failed_notifications` job function |
| `app/jobs/cleanup_tokens.py` | `cleanup_expired_tokens` job function |
| `app/jobs/__init__.py` | Package init |
| `alembic/versions/xxxx_add_notifications_retry_count.py` | Add `retry_count` column to `notifications` |
| `tests/unit/test_jobs.py` | Unit tests for both job functions |

---

## Data Model Changes

### `notifications.retry_count`

```sql
ALTER TABLE notifications ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
```

No other schema changes. The `refresh_tokens` table already has `expires_at` and `revoked_at` — cleanup job uses those directly.

---

## API

### User Management

```
PUT  /users/me           [any authenticated user]  — update own profile
GET  /users/             [PROPERTY_ADMIN+]          — list tenant users, ?limit, ?offset
POST /users/             [PROPERTY_ADMIN+]          — create user, returns temp_password once
PUT  /users/{id}         [PROPERTY_ADMIN+]          — update user (deactivate, profile, role)
```

### Admin

```
GET  /admin/tenants/     [SUPER_ADMIN]  — list all tenants (was unguarded)
GET  /admin/stats/       [SUPER_ADMIN]  — platform stats (was unguarded)
POST /admin/tenants/     [SUPER_ADMIN]  — create tenant (was 501)
PUT  /admin/tenants/{id} [SUPER_ADMIN]  — update tenant (was 501)
```

---

## Schemas

### `app/schemas/user.py` additions

```python
class UserUpdateMe(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole  # validated in endpoint: not SUPER_ADMIN
    phone_number: str | None = None
    unit_number: str | None = None

class UserCreateResponse(UserResponse):
    temp_password: str  # returned once, not stored

class UserUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None  # validated in endpoint: not SUPER_ADMIN
```

### `app/schemas/tenant.py` additions

```python
from typing import Literal

SubscriptionTier = Literal["basic", "pro", "enterprise"]

class TenantCreate(BaseModel):
    name: str
    slug: str  # URL-safe, unique
    subscription_tier: SubscriptionTier = "basic"
    settings: dict = {}

class TenantUpdate(BaseModel):
    name: str | None = None
    subscription_tier: SubscriptionTier | None = None
    settings: dict | None = None
```

---

## Error Responses

| Scenario | Status | Detail |
|----------|--------|--------|
| Wrong role for endpoint | 403 | "Insufficient permissions" |
| `POST /users/` with `role = SUPER_ADMIN` | 422 | "Cannot create SUPER_ADMIN accounts via API" |
| `PUT /users/{id}` sets `role = SUPER_ADMIN` | 422 | "Cannot assign SUPER_ADMIN role via API" |
| `PUT /users/{id}` where id == caller's own id | 400 | "Use PUT /users/me to update your own profile" |
| `PUT /users/{id}` user not in tenant | 404 | "User not found" (RLS returns empty result) |
| `POST /users/` with existing email in tenant | 409 | "Email already registered in this property" |
| `PUT /admin/tenants/{id}` tenant not found | 404 | "Tenant not found" |
| `POST /admin/tenants/` duplicate slug | 409 | "Slug already in use" |

---

## Testing

### Sub-spec A

**Unit — `tests/unit/test_require_role.py`:**
- `TENANT_USER` calling `require_role(PROPERTY_ADMIN)` → 403
- `PROPERTY_ADMIN` calling `require_role(PROPERTY_ADMIN, SUPER_ADMIN)` → passes
- `SUPER_ADMIN` calling `require_role(PROPERTY_ADMIN, SUPER_ADMIN)` → passes
- `SUPER_ADMIN` calling `require_role(SUPER_ADMIN)` → passes
- `PROPERTY_ADMIN` calling `require_role(SUPER_ADMIN)` → 403

**Integration — `tests/integration/test_user_management.py`:**
1. Seed tenant + PROPERTY_ADMIN user, login
2. `POST /users/` → 201, `temp_password` in response
3. Login with new user + temp_password → 200
4. `PUT /users/me` → 200, name updated
5. `GET /users/` → 200, list contains both users
6. `PUT /users/{id}` → set `is_active = false` → 200
7. Login with deactivated user → 401
8. `TENANT_USER` hits `GET /users/` → 403
9. `POST /users/` with `role = SUPER_ADMIN` → 422
10. `POST /users/` with duplicate email in same tenant → 409
11. `PUT /users/{id}` where id == caller's id → 400
12. `PROPERTY_ADMIN` in tenant A calls `PUT /users/{id}` for user in tenant B → 404 (RLS scopes result)

**Integration — `tests/integration/test_admin_endpoints.py`:**
1. Seed SUPER_ADMIN user (raw SQL, different tenant), login
2. `POST /admin/tenants/` → 201
3. `GET /admin/tenants/` → 200, list includes new tenant
4. `PUT /admin/tenants/{id}` → 200, tier updated
5. `GET /admin/stats/` → 200
6. `PROPERTY_ADMIN` hits `POST /admin/tenants/` → 403

### Sub-spec B

**Unit — `tests/unit/test_jobs.py`:**
- `retry_failed_notifications`: seed FAILED notification with retry_count=0, run job, assert status=SENT
- `retry_failed_notifications`: seed FAILED notification with retry_count=3, run job, assert untouched
- `retry_failed_notifications`: seed FAILED notification older than 24h, run job, assert untouched
- `cleanup_expired_tokens`: seed expired token (expires_at < now()-30d), run job, assert deleted
- `cleanup_expired_tokens`: seed recent valid token, run job, assert NOT deleted
- `cleanup_expired_tokens`: seed recently revoked token (revoked_at < now()-7d), run job, assert deleted

---

## Security Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Temp password delivery | Response body, one-time | No email infrastructure required; caller responsible for secure sharing |
| SUPER_ADMIN creation | Migrations only | Prevents privilege escalation via API |
| Role guard pattern | Explicit listing | No implicit hierarchy; every guard is auditable |
| ARQ retry window | 24 hours | Prevents indefinite retry of stale failures |
| Token cleanup retention | 30d expired / 7d revoked | Expired = may still be debugging; revoked = explicitly invalidated, shorter retention |
