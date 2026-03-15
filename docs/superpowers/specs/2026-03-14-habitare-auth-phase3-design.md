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
- `get_current_user` FastAPI dependency (JWT decode — returns `TokenData`, no DB hit)
- Replace `TenantIdDep` with `CurrentUserDep` on all Phase 2 endpoints
- WebSocket dashboard JWT auth via `?token` query param

**Out of scope:**
- User registration (users seeded via migrations or admin tooling)
- Social login / SSO
- 2FA / TOTP
- Rate limiting
- Role-based endpoint guards (beyond `is_active` check at login time)
- Token blocklist (deactivated users retain access until token expiry — 30 min max)

---

## Architecture

**Pattern:** Clean dependency replacement — `TenantIdDep` (X-Tenant-Id header stub) is removed and replaced with `CurrentUserDep` everywhere. `get_current_user` is purely JWT-based (no DB hit) and returns a `TokenData` dataclass with `user_id`, `tenant_id`, and `role`. Endpoints continue to manage their own `db.begin()` + `set_rls()` calls exactly as in Phase 2 — the only change is the source of `tenant_id` (JWT instead of header).

**Why no DB hit in `get_current_user`:** `SET LOCAL` is transaction-scoped in PostgreSQL. If the dependency opens and commits its own transaction to fetch the user, RLS is cleared before the endpoint's transaction begins. The JWT already contains the claims needed for routing and RLS — a DB lookup is redundant for the common case and would require every endpoint to abandon its own transaction control.

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
| `app/api/deps.py` | Add `get_current_user`, `CurrentUserDep`, `TokenData`; remove `TenantIdDep` |
| `app/api/v1/endpoints/visitors.py` | `TenantIdDep` → `CurrentUserDep`; use `current_user.tenant_id` for `set_rls()` |
| `app/api/v1/endpoints/visits.py` | same |
| `app/api/v1/endpoints/qr.py` | same; WS token auth |
| `app/api/v1/endpoints/invitations.py` | same |
| `app/api/v1/endpoints/notifications.py` | same; WS token auth |
| `app/api/v1/endpoints/admin.py` | same |
| `app/main.py` | Register auth + users routers |

---

## Data Model — `refresh_tokens`

```
refresh_tokens
├── id          UUID PK (default uuid4)
├── user_id     UUID FK → users.id NOT NULL (cascade delete)
├── tenant_id   UUID NOT NULL (stored for audit; NOT RLS-gated — see note)
├── token_hash  TEXT NOT NULL (SHA-256 hex digest of raw token — 64 chars)
├── expires_at  TIMESTAMPTZ NOT NULL
├── revoked_at  TIMESTAMPTZ nullable (null = still valid)
├── created_at  TIMESTAMPTZ NOT NULL (server default now())
```

**No RLS on `refresh_tokens`:** The `POST /auth/refresh` endpoint must look up a token by its hash before it knows the `tenant_id` — enabling RLS would create a deadlock (need tenant to query, need query to get tenant). Isolation is enforced instead by:
1. The SHA-256 hash is a 256-bit bearer credential — collision is computationally infeasible
2. `user_id` FK ensures the token is scoped to a specific user
3. Revocation query always filters by `token_hash AND user_id` — no cross-user revocation possible

`tenant_id` is retained for audit logging and future reporting, not for access control.

**Other notes:**
- No `updated_at` — tokens are create-once, revoke-once
- Unique index on `token_hash` for O(1) lookup
- Index on `user_id` for efficient per-user queries
- Argon2id hashes with argon2-cffi defaults produce ~97-character strings — well within `Text` column

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
4. `verify_password(password, user.password_hash)` — 401 on mismatch (same error message as step 3 — no oracle)
5. Update `user.last_login_at = now()`
6. Generate raw refresh token (`secrets.token_urlsafe(32)`)
7. Insert `RefreshToken(token_hash=sha256(raw), user_id, tenant_id, expires_at=now()+14d)`
8. Generate access token JWT (`sub=str(user_id)`, `tenant_id=str(tenant_id)`, `role`, `exp`, `iat`)
9. Commit transaction
10. Return `TokenResponse`

**Response:**
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<raw>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

`expires_in` is derived from `settings.access_token_expire_minutes * 60` — not hardcoded.

### POST /auth/refresh

**Request:** `{ "refresh_token": "<raw>" }`

**Steps:**
1. SHA-256 hash the raw token
2. Look up `RefreshToken` by `token_hash` — no RLS needed (see data model note)
3. 401 if not found, `revoked_at IS NOT NULL`, or `expires_at < now()`
4. In same transaction:
   - Set `revoked_at = now()` on old token
   - Insert new `RefreshToken` for same `user_id` + `tenant_id`
   - Generate new access + refresh token pair
5. Commit, return new `TokenResponse`

**Revoked token presented:** Return 401 and log a warning — indicates possible token theft.

### POST /auth/logout

**Auth:** `CurrentUserDep` (access token required)

**Request:** `{ "refresh_token": "<raw>" }` (optional)

**Steps:**
1. If `refresh_token` provided:
   - SHA-256 hash it
   - Look up by `token_hash AND user_id = current_user.user_id` — 404 silently ignored
   - Set `revoked_at = now()`
2. Return 204

**Note:** Scoping revocation to `user_id = current_user.user_id` prevents a user from revoking another user's refresh token, even within the same tenant.

### GET /users/me

**Auth:** `CurrentUserDep`

**Steps:**
1. Extract `tenant_id` from `current_user` (JWT claim)
2. Open transaction, `SET LOCAL app.current_tenant_id = current_user.tenant_id`
3. Fetch `User` by `current_user.user_id`
4. Return `UserResponse`

**Response:** `UserResponse(id, email, full_name, role, tenant_id, is_active)`

---

## `TokenData` + `get_current_user` Dependency

```python
from dataclasses import dataclass

@dataclass
class TokenData:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenData:
    """Decode JWT. No DB hit — RLS is managed per-endpoint as in Phase 2."""
    payload = decode_token(token)   # raises HTTP 401 on invalid/expired/tampered
    return TokenData(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=payload["role"],
    )

CurrentUserDep = Annotated[TokenData, Depends(get_current_user)]
```

**All protected Phase 2 endpoints:**
- Replace `tenant_id: TenantIdDep` with `current_user: CurrentUserDep`
- Derive tenant via `current_user.tenant_id`
- Continue calling `set_rls(db, current_user.tenant_id)` inside `async with db.begin():` — exactly as before

**`GET /users/me`** is the only endpoint that fetches a `User` ORM object. It does so inside its own `db.begin()` block after calling `set_rls()`.

---

## WebSocket Auth

**Endpoint:** `GET /ws/dashboard?token=<access_token>`

**Handler:**
1. Extract `token` from query params — close with code `4001` ("Unauthorized") if missing
2. `decode_token(token)` — close with `4001` if invalid or expired
3. `await ws_manager.connect(tenant_id, websocket)` — tenant_id from JWT payload

No DB hit. Access tokens are self-contained. Close code `4001` is defined as "Unauthorized" for this application (4000–4999 are reserved for application use per the WebSocket spec).

---

## `decode_token` Contract

```python
def decode_token(token: str) -> dict:
    """Decode and validate JWT. Raises HTTP 401 on any failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        # Validate required claims present
        if not all(k in payload for k in ("sub", "tenant_id", "role")):
            raise ValueError("Missing claims")
        return payload
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

`iat` is included in the JWT payload for audit purposes but is not validated beyond PyJWT's built-in checks. This is intentional for Phase 3 — forced rotation requires a blocklist (out of scope).

---

## Security Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Password hashing | Argon2id via `argon2-cffi` defaults | OWASP recommended; argon2-cffi defaults (~97 char output) fit `Text` column |
| JWT algorithm | HS256 | Sufficient for single-service; RS256 adds complexity with no benefit here |
| Refresh token storage | SHA-256 hash only | Raw token is a credential; never persist plaintext |
| Revoked token response | 401 (not 403) | Leaks no information about token existence |
| `tenant_id` in login body | Yes | Required to set RLS before user lookup; can't query `users` table without it |
| WebSocket auth | Query param `?token` | Browser WebSocket API doesn't support custom headers |
| No RLS on `refresh_tokens` | Intentional | Token hash is a bearer credential — lookup-by-hash provides isolation without RLS |
| No DB hit in `get_current_user` | Intentional | Avoids RLS transaction lifecycle conflict; JWT claims are sufficient |
| Deactivated users | Retain access until token expiry | No blocklist in Phase 3; max exposure is 30 min (access token lifetime) |

---

## JWT Payload

```json
{
  "sub": "<user_id as string>",
  "tenant_id": "<tenant_id as string>",
  "role": "tenant_user",
  "exp": 1234567890,
  "iat": 1234567890
}
```

`iat` is included but not validated beyond PyJWT built-ins (Phase 3 scope).

---

## Error Responses

| Scenario | Status | Detail |
|----------|--------|--------|
| User not found or wrong password | 401 | "Invalid email or password" (same message — no oracle) |
| Inactive user at login | 401 | "Invalid email or password" |
| Invalid/expired access token | 401 | "Could not validate credentials" |
| Invalid/revoked refresh token | 401 | "Invalid or expired refresh token" |
| Invalid tenant_id UUID in login | 400 | "Invalid tenant ID" |

All 401s include `WWW-Authenticate: Bearer` header.

---

## Testing

### Unit tests
- `test_security.py`: hash produces argon2 string, verify returns True for correct password, False for wrong, False for empty string
- `test_jwt.py`: encode→decode round-trip preserves all claims, expired token raises 401, tampered signature raises 401, missing claim raises 401

### Integration tests
- `test_auth_flow.py`:
  1. Seed tenant + user with hashed password
  2. `POST /auth/login` → 200, receive tokens
  3. `GET /users/me` with access token → 200, correct user
  4. `POST /auth/refresh` → 200, new token pair
  5. `POST /auth/logout` with refresh token → 204
  6. `POST /auth/refresh` with old (revoked) refresh token → 401
  7. Cross-tenant: login as tenant A, use token with tenant B visitor endpoint → 404 (RLS scopes results)

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

-- No RLS: refresh token lookup must precede knowing the tenant_id.
-- Isolation provided by token_hash uniqueness + user_id FK.
```
