# Habitare Auth — Phase 3 Design Spec

**Date:** 2026-03-14
**Project:** Habitare QR-Based Visitor Management System
**Phase:** 3 — Authentication Completion
**Stack:** FastAPI · PostgreSQL 17 (RLS) · SQLAlchemy 2.0 async · Python 3.13 · PyJWT · argon2-cffi

---

## Goal

Complete the authentication layer that was deferred during Phase 2. Replace the `X-Tenant-Id` header stub with real JWT-based auth across all protected endpoints. Add DB-backed refresh tokens with rotation. Protect the WebSocket dashboard.

---

## Scope

**In scope:**
- Password hashing service (Argon2id)
- JWT creation + validation (`access_token` HS256 30-min, `refresh_token` opaque 14-day)
- `RefreshToken` model + migration
- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`
- `GET /users/me`
- `get_current_user` FastAPI dependency (JWT decode + RLS set)
- Replace `TenantIdDep` with `CurrentUserDep` on all Phase 2 endpoints
- WebSocket dashboard JWT auth via `?token` query param

**Out of scope:**
- User registration (users seeded via migrations or admin tooling)
- Social login / SSO
- 2FA / TOTP
- Rate limiting
- Role-based endpoint guards (beyond `is_active` check)

---

## Architecture

**Pattern:** Clean dependency replacement — `TenantIdDep` (X-Tenant-Id header stub) is removed and replaced with `CurrentUserDep` everywhere. `get_current_user` is the single place that validates JWT, sets RLS, and returns the authenticated `User`. No middleware.

**Auth flow:** JWT access token (short-lived, stateless) + DB-backed refresh token (long-lived, revocable). Refresh tokens are stored as SHA-256 hashes — raw token is never persisted.

---

## Files

### New

| File | Responsibility |
|------|---------------|
| `app/core/security.py` | Argon2id hashing: `hash_password`, `verify_password` |
| `app/core/jwt.py` | JWT creation + validation: `create_access_token`, `decode_token` |
| `app/models/token.py` | `RefreshToken` ORM model |
| `app/schemas/auth.py` | `LoginRequest`, `TokenResponse`, `RefreshRequest` |
| `app/schemas/user.py` | `UserResponse` |
| `app/api/v1/endpoints/auth.py` | `POST /auth/login`, `/auth/refresh`, `/auth/logout` |
| `app/api/v1/endpoints/users.py` | `GET /users/me` |
| `alembic/versions/xxxx_add_refresh_tokens.py` | `refresh_tokens` table migration |
| `tests/unit/test_security.py` | Argon2 hash/verify unit tests |
| `tests/unit/test_jwt.py` | JWT encode/decode unit tests |
| `tests/integration/test_auth_flow.py` | Login → refresh → logout integration test |

### Modified

| File | Change |
|------|--------|
| `app/api/deps.py` | Add `get_current_user`, `CurrentUserDep`; remove `TenantIdDep` |
| `app/api/v1/endpoints/visitors.py` | `TenantIdDep` → `CurrentUserDep` |
| `app/api/v1/endpoints/visits.py` | `TenantIdDep` → `CurrentUserDep` |
| `app/api/v1/endpoints/qr.py` | `TenantIdDep` → `CurrentUserDep`; WS token auth |
| `app/api/v1/endpoints/invitations.py` | `TenantIdDep` → `CurrentUserDep` |
| `app/api/v1/endpoints/notifications.py` | `TenantIdDep` → `CurrentUserDep`; WS token auth |
| `app/api/v1/endpoints/admin.py` | `TenantIdDep` → `CurrentUserDep` |
| `app/main.py` | Register auth + users routers |

---

## Data Model — `refresh_tokens`

```
refresh_tokens
├── id          UUID PK (default uuid4)
├── user_id     UUID FK → users.id NOT NULL (cascade delete)
├── tenant_id   UUID NOT NULL (for RLS — same pattern as all tables)
├── token_hash  TEXT NOT NULL (SHA-256 hex digest of raw token)
├── expires_at  TIMESTAMPTZ NOT NULL
├── revoked_at  TIMESTAMPTZ nullable (null = still valid)
├── created_at  TIMESTAMPTZ NOT NULL (server default now())
```

**Notes:**
- No `TenantMixin` (tokens aren't a tenant resource) but `tenant_id` stored for RLS consistency
- No `updated_at` — tokens are create-once, revoke-once
- Index on `token_hash` for O(1) lookup at refresh time
- Index on `user_id` for efficient logout-all-devices queries (future)
- RLS policy: `tenant_id = current_setting('app.current_tenant_id')`

---

## Auth Flows

### POST /auth/login

**Request:**
```json
{ "email": "staff@example.com", "password": "secret", "tenant_id": "<uuid>" }
```

**Steps:**
1. Parse `tenant_id` — 400 if invalid UUID
2. Open transaction, `SET LOCAL app.current_tenant_id = tenant_id`
3. Fetch `User` by `email` — 401 if not found or `is_active=False`
4. `verify_password(password, user.password_hash)` — 401 on mismatch
5. Update `user.last_login_at = now()`
6. Generate raw refresh token (`secrets.token_urlsafe(32)`)
7. Insert `RefreshToken(token_hash=sha256(raw), expires_at=now()+14d)`
8. Generate access token JWT (`sub=user_id`, `tenant_id`, `role`, `exp`)
9. Return `TokenResponse`

**Response:**
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<raw>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST /auth/refresh

**Request:** `{ "refresh_token": "<raw>" }`

**Steps:**
1. SHA-256 hash the raw token
2. `SET LOCAL` with tenant_id from matched row (select by hash)
3. 401 if not found, `revoked_at IS NOT NULL`, or `expires_at < now()`
4. In same transaction: set `revoked_at = now()` on old token, insert new `RefreshToken`
5. Return new `TokenResponse` (new access + refresh tokens)

**Revoked token presented:** Return 401 — treat as possible token theft indicator (log warning).

### POST /auth/logout

**Auth:** `CurrentUserDep` (access token required)

**Request:** `{ "refresh_token": "<raw>" }` (optional)

**Steps:**
1. If `refresh_token` provided: hash it, set `revoked_at = now()`
2. Return 204

### GET /users/me

**Auth:** `CurrentUserDep`

**Response:** `UserResponse(id, email, full_name, role, tenant_id, is_active)`

---

## `get_current_user` Dependency

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSessionDep,
) -> User:
    payload = decode_token(token)          # raises HTTP 401 on invalid/expired
    user_id = uuid.UUID(payload["sub"])
    tenant_id = uuid.UUID(payload["tenant_id"])

    async with db.begin():
        await set_rls(db, tenant_id)
        user = await db.get(User, user_id)

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

CurrentUserDep = Annotated[User, Depends(get_current_user)]
```

**All protected Phase 2 endpoints:**
- Replace `tenant_id: TenantIdDep` with `current_user: CurrentUserDep`
- Derive tenant via `current_user.tenant_id`
- RLS is already set by `get_current_user` — endpoints do NOT call `set_rls()` again

---

## WebSocket Auth

**Endpoint:** `GET /ws/dashboard?token=<access_token>`

**Handler:**
1. Extract `token` from query params — 4001 close if missing
2. `decode_token(token)` — 4001 close if invalid or expired
3. Verify user is active (DB lookup optional — access tokens are stateless; skip for performance)
4. `await ws_manager.connect(tenant_id, websocket)`

No DB hit required for WebSocket auth — access tokens are self-contained.

---

## Security Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Password hashing | Argon2id via `argon2-cffi` | OWASP recommended; already a project dependency |
| JWT algorithm | HS256 | Sufficient for single-service; RS256 adds complexity with no benefit here |
| Refresh token storage | SHA-256 hash only | Raw token is a credential; never persist plaintext |
| Revoked token response | 401 (not 403) | Leaks no information about token existence |
| `tenant_id` in login body | Yes | Required to set RLS before user lookup; can't query users table without it |
| WebSocket auth | Query param `?token` | Browser WebSocket API doesn't support custom headers |

---

## JWT Payload

```json
{
  "sub": "<user_id>",
  "tenant_id": "<tenant_id>",
  "role": "tenant_user",
  "exp": 1234567890,
  "iat": 1234567890
}
```

---

## Error Responses

| Scenario | Status | Detail |
|----------|--------|--------|
| Invalid credentials | 401 | "Invalid email or password" |
| Inactive user | 401 | "User not found or inactive" |
| Invalid/expired access token | 401 | "Could not validate credentials" |
| Invalid/revoked refresh token | 401 | "Invalid or expired refresh token" |
| Invalid tenant_id UUID | 400 | "Invalid tenant ID" |

All 401s include `WWW-Authenticate: Bearer` header.

---

## Testing

### Unit tests
- `test_security.py`: hash produces argon2 string, verify returns True for correct password, False for wrong, False for empty hash
- `test_jwt.py`: encode→decode round-trip, expired token raises, tampered signature raises, missing claim raises

### Integration tests
- `test_auth_flow.py`: seed user → login → get `/users/me` → refresh → logout → verify refresh token revoked → verify old refresh token rejected
- Cross-tenant: login as tenant A user, attempt to use token against tenant B data → 401/404

---

## Migration

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens(user_id);

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY;

CREATE POLICY refresh_tokens_tenant_isolation ON refresh_tokens
    USING (tenant_id::text = current_setting('app.current_tenant_id', TRUE))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', TRUE));
```
