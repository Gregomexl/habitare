# Phase 4 — RBAC, User Management & Background Jobs Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add role-based access control, complete user management endpoints, implement admin tenant CRUD, and wire up ARQ background jobs for email retry and token cleanup.

**Architecture:** `require_role()` is a dependency factory that returns an async function FastAPI injects — consistent with the existing `CurrentUserDep` pattern. User management endpoints call `set_rls()` for tenant isolation; admin endpoints skip it (tenants table has no RLS). ARQ worker groups failed notifications by `tenant_id` and sets `SET LOCAL` per group to satisfy RLS.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 async · PostgreSQL 17 (RLS) · Python 3.13 · ARQ · Redis 7 · argon2-cffi · pytest-asyncio

---

## File Map

### Sub-spec A — RBAC + User Management

| File | Action | Responsibility |
|------|--------|----------------|
| `app/api/deps.py` | Modify | Add `require_role()`, `RequireAdminDep`, `RequireSuperAdminDep` |
| `app/schemas/user.py` | Modify | Add `UserUpdateMe`, `UserCreate`, `UserCreateResponse`, `UserUpdate`; extend `UserResponse` |
| `app/schemas/tenant.py` | Modify | Add `TenantCreate`, `TenantUpdate` |
| `alembic/versions/xxxx_add_users_email_unique.py` | Create | Add `UNIQUE (tenant_id, email)` index on users |
| `app/api/v1/endpoints/users.py` | Modify | Add `PUT /users/me`, `GET /users/`, `POST /users/`, `PUT /users/{id}` |
| `app/api/v1/endpoints/admin.py` | Modify | Add role guards, implement `POST /admin/tenants/`, `PUT /admin/tenants/{id}` |
| `tests/unit/test_require_role.py` | Create | Unit tests for `require_role()` |
| `tests/integration/test_user_management.py` | Create | Integration tests for user management flows |
| `tests/integration/test_admin_endpoints.py` | Create | Integration tests for admin endpoints |

### Sub-spec B — Background Jobs

| File | Action | Responsibility |
|------|--------|----------------|
| `app/models/notification.py` | Modify | Add `retry_count` column |
| `alembic/versions/xxxx_add_retry_count.py` | Create | Migration: `ALTER TABLE notifications ADD COLUMN retry_count` |
| `app/jobs/__init__.py` | Create | Package init (empty) |
| `app/jobs/retry_notifications.py` | Create | `retry_failed_notifications` ARQ cron job |
| `app/jobs/cleanup_tokens.py` | Create | `cleanup_expired_tokens` ARQ cron job |
| `app/worker.py` | Create | ARQ `WorkerSettings` entry point |
| `tests/unit/test_jobs.py` | Create | Unit tests for both job functions |

---

## Chunk 1: RBAC Foundation

### Task 1: `require_role()` dependency + unit tests

**Files:**
- Modify: `app/api/deps.py`
- Create: `tests/unit/test_require_role.py`

**Codebase context:** `app/api/deps.py` already has `TokenData`, `CurrentUserDep`, `get_current_user`, `set_rls`, `get_db`. The pattern for typed dependency aliases is `Annotated[ReturnType, Depends(fn)]`. `TokenData.role` is `str`; `UserRole` extends `str, Enum` so `"property_admin" in (UserRole.PROPERTY_ADMIN,)` evaluates `True` in Python.

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/test_require_role.py
import uuid
import pytest
from fastapi import HTTPException

from app.api.deps import TokenData, require_role
from app.models.user import UserRole


def _token(role: UserRole) -> TokenData:
    return TokenData(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=role)


@pytest.mark.asyncio
async def test_correct_role_passes():
    check = require_role(UserRole.PROPERTY_ADMIN)
    result = await check(_token(UserRole.PROPERTY_ADMIN))
    assert result.role == UserRole.PROPERTY_ADMIN


@pytest.mark.asyncio
async def test_wrong_role_raises_403():
    check = require_role(UserRole.PROPERTY_ADMIN)
    with pytest.raises(HTTPException) as exc:
        await check(_token(UserRole.TENANT_USER))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient permissions"


@pytest.mark.asyncio
async def test_super_admin_passes_admin_guard():
    check = require_role(UserRole.PROPERTY_ADMIN, UserRole.SUPER_ADMIN)
    result = await check(_token(UserRole.SUPER_ADMIN))
    assert result.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_super_admin_only_guard():
    check = require_role(UserRole.SUPER_ADMIN)
    result = await check(_token(UserRole.SUPER_ADMIN))
    assert result.role == UserRole.SUPER_ADMIN


@pytest.mark.asyncio
async def test_property_admin_fails_super_admin_guard():
    check = require_role(UserRole.SUPER_ADMIN)
    with pytest.raises(HTTPException) as exc:
        await check(_token(UserRole.PROPERTY_ADMIN))
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/unit/test_require_role.py -v
```
Expected: `ImportError: cannot import name 'require_role'`

- [ ] **Step 3: Implement `require_role()` in `app/api/deps.py`**

Add this import at the top of `app/api/deps.py` (after existing imports):
```python
from app.models.user import UserRole
```

Add these after `CurrentUserDep = ...`:
```python
def require_role(*roles: UserRole):
    """Dependency factory: raises 403 if current user's role is not in `roles`.

    Usage:
        async def my_endpoint(current_user: RequireAdminDep, ...): ...

    Note: require_role() returns the inner async function (not Depends). Wrap in
    Annotated[TokenData, Depends(...)] to create typed aliases (see below).
    """
    async def check(current_user: CurrentUserDep) -> TokenData:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return check


RequireAdminDep = Annotated[TokenData, Depends(require_role(UserRole.PROPERTY_ADMIN, UserRole.SUPER_ADMIN))]
RequireSuperAdminDep = Annotated[TokenData, Depends(require_role(UserRole.SUPER_ADMIN))]
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/unit/test_require_role.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/api/deps.py tests/unit/test_require_role.py
git commit -m "feat(deps): add require_role() dependency factory with RequireAdminDep and RequireSuperAdminDep"
```

---

### Task 2: Schemas — user + tenant

**Files:**
- Modify: `app/schemas/user.py`
- Modify: `app/schemas/tenant.py`

**Codebase context:**

Current `app/schemas/user.py`:
```python
import uuid
from pydantic import BaseModel
from app.models.user import UserRole

class UserResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    tenant_id: uuid.UUID
    is_active: bool
```

`User` model has `unit_number: str | None` and `phone_number: str | None` — add these to `UserResponse` too.

Current `app/schemas/tenant.py` only has `TenantResponse`. `Tenant` model has `name`, `slug`, `subscription_tier`, `settings`, `deleted_at`.

- [ ] **Step 1: Replace `app/schemas/user.py`**

```python
import uuid
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    full_name: str | None
    phone_number: str | None
    unit_number: str | None
    role: UserRole
    tenant_id: uuid.UUID
    is_active: bool


class UserUpdateMe(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    phone_number: str | None = None
    unit_number: str | None = None


class UserCreateResponse(UserResponse):
    temp_password: str  # returned once, never stored plaintext


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    unit_number: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None
```

- [ ] **Step 2: Add to `app/schemas/tenant.py`**

Append to the existing file (after `TenantResponse`):

```python
from typing import Literal

SubscriptionTier = Literal["basic", "pro", "enterprise"]


class TenantCreate(BaseModel):
    name: str
    slug: str
    subscription_tier: SubscriptionTier = "basic"
    settings: dict = {}


class TenantUpdate(BaseModel):
    name: str | None = None
    subscription_tier: SubscriptionTier | None = None
    settings: dict | None = None
```

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "
from app.schemas.user import UserResponse, UserUpdateMe, UserCreate, UserCreateResponse, UserUpdate
from app.schemas.tenant import TenantCreate, TenantUpdate
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3.5: Add unique constraint migration for `(tenant_id, email)` on users**

The `User` model's unique constraint on `(tenant_id, email)` was commented out in the initial migration. Create it now so duplicate email detection works.

```bash
uv run alembic revision -m "add unique constraint users tenant_id email"
```

Open the generated file and write:

```python
def upgrade() -> None:
    op.create_index(
        "uq_users_tenant_email",
        "users",
        ["tenant_id", "email"],
        unique=True,
    )

def downgrade() -> None:
    op.drop_index("uq_users_tenant_email", table_name="users")
```

Apply it:
```bash
uv run alembic upgrade head
```

Expected: `Running upgrade ... add unique constraint users tenant_id email`

- [ ] **Step 4: Run existing tests to confirm nothing broke**

```bash
uv run pytest tests/unit/ tests/integration/test_auth_flow.py -q
```
Expected: all pass (the auth flow test uses `UserResponse` via `GET /users/me`).

- [ ] **Step 5: Commit**

```bash
git add app/schemas/user.py app/schemas/tenant.py alembic/versions/
git commit -m "feat(schemas): add user management and tenant CRUD schemas; add unique constraint on users(tenant_id, email)"
```

---

## Chunk 2: User Management Endpoints

### Task 3: User management endpoints

**Files:**
- Modify: `app/api/v1/endpoints/users.py`

**Codebase context:**

Current `app/api/v1/endpoints/users.py` has only `GET /users/me`. Pattern from other endpoints:
```python
async with db.begin():
    await set_rls(db, current_user.tenant_id)
    result = await db.execute(select(User).where(...))
```

`User` model fields: `id`, `email`, `password_hash`, `full_name`, `unit_number`, `phone_number`, `role`, `email_verified`, `is_active`, `last_login_at`, `tenant_id`, `created_at`, `updated_at`.

Temp password: `secrets.token_urlsafe(12)` → 16 URL-safe characters. Hash with `hash_password` from `app.core.security`.

- [ ] **Step 1: Rewrite `app/api/v1/endpoints/users.py`**

```python
"""User endpoints: profile retrieval and management."""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep, CurrentUserDep, RequireAdminDep, set_rls
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreate,
    UserCreateResponse,
    UserResponse,
    UserUpdate,
    UserUpdateMe,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUserDep, db: AsyncSessionDep) -> UserResponse:
    """Return the authenticated user's profile."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == current_user.user_id))
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserResponse.model_validate(user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateMe,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> UserResponse:
    """Update the authenticated user's own profile."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == current_user.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone_number is not None:
            user.phone_number = body.phone_number
        if body.unit_number is not None:
            user.unit_number = body.unit_number
        user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)


@router.get("/", response_model=list[UserResponse])
async def list_users(
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
    limit: int = 50,
    offset: int = 0,
) -> list[UserResponse]:
    """List all users in the caller's tenant. Requires PROPERTY_ADMIN or SUPER_ADMIN."""
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(
            select(User)
            .order_by(User.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/", response_model=UserCreateResponse, status_code=201)
async def create_user(
    body: UserCreate,
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
) -> UserCreateResponse:
    """Create a staff account. Returns a one-time temp password. Requires PROPERTY_ADMIN+."""
    if body.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=422, detail="Cannot create SUPER_ADMIN accounts via API")

    temp_password = secrets.token_urlsafe(12)
    pw_hash = hash_password(temp_password)

    new_user = User(
        tenant_id=current_user.tenant_id,
        email=body.email,
        password_hash=pw_hash,
        full_name=body.full_name,
        phone_number=body.phone_number,
        unit_number=body.unit_number,
        role=body.role,
        is_active=True,
        email_verified=False,
    )

    try:
        async with db.begin():
            await set_rls(db, current_user.tenant_id)
            db.add(new_user)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered in this property")

    # model_validate on the ORM object gives us all UserResponse fields;
    # then inject temp_password (not stored on the model) for the one-time response.
    return UserCreateResponse(
        **UserResponse.model_validate(new_user).model_dump(),
        temp_password=temp_password,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: RequireAdminDep,
    db: AsyncSessionDep,
) -> UserResponse:
    """Update a user in the caller's tenant. Requires PROPERTY_ADMIN+."""
    if user_id == current_user.user_id:
        raise HTTPException(
            status_code=400, detail="Use PUT /users/me to update your own profile"
        )

    if body.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=422, detail="Cannot assign SUPER_ADMIN role via API")

    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.full_name is not None:
            user.full_name = body.full_name
        if body.phone_number is not None:
            user.phone_number = body.phone_number
        if body.unit_number is not None:
            user.unit_number = body.unit_number
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.role is not None:
            user.role = body.role
        user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)
```

- [ ] **Step 2: Verify the app still imports cleanly**

```bash
uv run python -c "from app.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/endpoints/users.py
git commit -m "feat(endpoints): add PUT /users/me, GET /users/, POST /users/, PUT /users/{id}"
```

---

### Task 4: Admin endpoints — guards + implement POST/PUT tenants

**Files:**
- Modify: `app/api/v1/endpoints/admin.py`

**Codebase context:** `Tenant` model has `id`, `name`, `slug` (unique), `subscription_tier`, `settings`, `deleted_at`, `created_at`, `updated_at`. Admin endpoints do NOT call `set_rls()` — the `tenants` table has no RLS policy.

- [ ] **Step 1: Rewrite `app/api/v1/endpoints/admin.py`**

```python
"""Admin endpoints — SUPER_ADMIN only. No set_rls() — tenants table has no RLS."""
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.api.deps import AsyncSessionDep, RequireSuperAdminDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants/", response_model=list[TenantResponse])
async def list_tenants(
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
    limit: int = 50,
    offset: int = 0,
):
    """List all tenants. SUPER_ADMIN only."""
    async with db.begin():
        result = await db.execute(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(min(limit, 200)).offset(offset)
        )
        return result.scalars().all()


@router.get("/stats/")
async def get_stats(current_user: RequireSuperAdminDep, db: AsyncSessionDep):
    """Platform stats. SUPER_ADMIN only."""
    async with db.begin():
        tenant_count = await db.execute(text("SELECT COUNT(*) FROM tenants"))
        return {"total_tenants": tenant_count.scalar()}


@router.post("/tenants/", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
):
    """Create a new tenant. SUPER_ADMIN only. No set_rls() — tenants has no RLS."""
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        subscription_tier=body.subscription_tier,
        settings=body.settings,
    )
    try:
        async with db.begin():
            db.add(tenant)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Slug already in use")
    return tenant


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
):
    """Update a tenant. SUPER_ADMIN only."""
    async with db.begin():
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if body.name is not None:
            tenant.name = body.name
        if body.subscription_tier is not None:
            tenant.subscription_tier = body.subscription_tier
        if body.settings is not None:
            tenant.settings = body.settings
        tenant.updated_at = datetime.now(timezone.utc)

    return tenant
```

- [ ] **Step 2: Verify imports**

```bash
uv run python -c "from app.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/endpoints/admin.py
git commit -m "feat(endpoints): implement admin tenant CRUD with SUPER_ADMIN guards"
```

---

### Task 5: Integration tests — user management

**Files:**
- Create: `tests/integration/test_user_management.py`

**Codebase context:** Follow the pattern from `tests/integration/test_auth_flow.py`. The fixture seeds a tenant + user with raw SQL, logs in via `POST /api/v1/auth/login` to get a JWT, uses the JWT for API calls. `asyncio_mode = "auto"` is set in `pyproject.toml`. Module-scoped fixture uses `loop_scope="module"`. The `users` table `userrole` enum uses uppercase values in PostgreSQL: `'PROPERTY_ADMIN'`, `'TENANT_USER'`.

- [ ] **Step 1: Write the test file**

```python
# tests/integration/test_user_management.py
"""Integration tests: user management endpoints."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.core.database import async_session, engine
from app.core.security import hash_password
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="module")

TENANT_ID = str(uuid.uuid4())
ADMIN_EMAIL = f"admin-{uuid.uuid4().hex[:8]}@test.com"
ADMIN_PASSWORD = "admin-password-123"
ACCESS_TOKEN: str = ""


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def seed_data():
    global ACCESS_TOKEN
    admin_id = str(uuid.uuid4())
    pw_hash = hash_password(ADMIN_PASSWORD)

    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, 'Mgmt Tenant', :slug, 'basic', '{}', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": TENANT_ID, "slug": f"mgmt-{TENANT_ID[:8]}"},
            )
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'PROPERTY_ADMIN', true, true, now(), now())"
                ),
                {"id": admin_id, "tid": TENANT_ID, "email": ADMIN_EMAIL, "pw": pw_hash},
            )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        ACCESS_TOKEN = resp.json()["access_token"]

    yield

    # Two separate transactions: users (RLS) then tenants (no RLS)
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            await db.execute(text("DELETE FROM users WHERE tenant_id = :tid"), {"tid": TENANT_ID})
        async with db.begin():
            await db.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": TENANT_ID})
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def auth_headers() -> dict:
    return {"Authorization": f"Bearer {ACCESS_TOKEN}"}


async def test_put_users_me_updates_profile(client):
    resp = await client.put(
        "/api/v1/users/me",
        json={"full_name": "Updated Admin"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Admin"


async def test_post_users_creates_staff_returns_temp_password(client):
    resp = await client.post(
        "/api/v1/users/",
        json={"email": f"staff-{uuid.uuid4().hex[:6]}@test.com", "role": "tenant_user"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "temp_password" in data
    assert len(data["temp_password"]) >= 12


async def test_new_user_can_login_with_temp_password(client):
    email = f"login-test-{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post(
        "/api/v1/users/",
        json={"email": email, "role": "tenant_user"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 201
    temp_pw = resp.json()["temp_password"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": temp_pw, "tenant_id": TENANT_ID},
    )
    assert login.status_code == 200


async def test_get_users_returns_list(client):
    resp = await client.get("/api/v1/users/", headers=await auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    emails = [u["email"] for u in resp.json()]
    assert ADMIN_EMAIL in emails


async def test_put_users_id_deactivates_user(client):
    # Create a user to deactivate
    email = f"deact-{uuid.uuid4().hex[:6]}@test.com"
    create = await client.post(
        "/api/v1/users/",
        json={"email": email, "role": "tenant_user"},
        headers=await auth_headers(),
    )
    user_id = create.json()["id"]
    temp_pw = create.json()["temp_password"]

    resp = await client.put(
        f"/api/v1/users/{user_id}",
        json={"is_active": False},
        headers=await auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Deactivated user cannot login
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": temp_pw, "tenant_id": TENANT_ID},
    )
    assert login.status_code == 401


async def test_tenant_user_cannot_list_users(client):
    # Create a tenant_user and login as them
    email = f"tu-{uuid.uuid4().hex[:6]}@test.com"
    create = await client.post(
        "/api/v1/users/",
        json={"email": email, "role": "tenant_user"},
        headers=await auth_headers(),
    )
    temp_pw = create.json()["temp_password"]
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": temp_pw, "tenant_id": TENANT_ID},
    )
    tu_token = login.json()["access_token"]

    resp = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {tu_token}"},
    )
    assert resp.status_code == 403


async def test_post_users_with_super_admin_role_returns_422(client):
    resp = await client.post(
        "/api/v1/users/",
        json={"email": f"sa-{uuid.uuid4().hex[:6]}@test.com", "role": "super_admin"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 422


async def test_post_users_duplicate_email_returns_409(client):
    email = f"dup-{uuid.uuid4().hex[:6]}@test.com"
    await client.post(
        "/api/v1/users/",
        json={"email": email, "role": "tenant_user"},
        headers=await auth_headers(),
    )
    resp = await client.post(
        "/api/v1/users/",
        json={"email": email, "role": "tenant_user"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 409


async def test_put_users_self_returns_400(client):
    me = await client.get("/api/v1/users/me", headers=await auth_headers())
    my_id = me.json()["id"]
    resp = await client.put(
        f"/api/v1/users/{my_id}",
        json={"full_name": "Self Edit"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 400


async def test_put_users_cross_tenant_returns_404(client):
    # Use a random UUID that doesn't exist in this tenant
    fake_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/v1/users/{fake_id}",
        json={"full_name": "Cross Tenant"},
        headers=await auth_headers(),
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/integration/test_user_management.py -v --tb=short
```
Expected: `10 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_user_management.py
git commit -m "test(integration): add user management integration tests"
```

---

### Task 6: Integration tests — admin endpoints

**Files:**
- Create: `tests/integration/test_admin_endpoints.py`

**Codebase context:** `SUPER_ADMIN` must be seeded via raw SQL — cannot create via API. The `tenants` table has no RLS so `SUPER_ADMIN` user can be inserted with any `tenant_id` (use a separate "platform" tenant). `TenantResponse` has `id`, `name`, `subscription_tier`, `created_at`.

- [ ] **Step 1: Write the test file**

```python
# tests/integration/test_admin_endpoints.py
"""Integration tests: admin endpoints (SUPER_ADMIN only)."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.core.database import async_session, engine
from app.core.security import hash_password
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="module")

PLATFORM_TENANT_ID = str(uuid.uuid4())
SUPER_ADMIN_EMAIL = f"superadmin-{uuid.uuid4().hex[:8]}@test.com"
SUPER_ADMIN_PASSWORD = "super-admin-pw-123"
ADMIN_TOKEN: str = ""
PROPERTY_ADMIN_TOKEN: str = ""
PROPERTY_TENANT_ID = str(uuid.uuid4())
PROPERTY_ADMIN_EMAIL = f"propadmin-{uuid.uuid4().hex[:8]}@test.com"
PROPERTY_ADMIN_PASSWORD = "prop-admin-pw-123"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def seed_data():
    global ADMIN_TOKEN, PROPERTY_ADMIN_TOKEN
    sa_id = str(uuid.uuid4())
    pa_id = str(uuid.uuid4())
    sa_hash = hash_password(SUPER_ADMIN_PASSWORD)
    pa_hash = hash_password(PROPERTY_ADMIN_PASSWORD)

    async with async_session() as db:
        async with db.begin():
            # Platform tenant (for super admin)
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, 'Platform', :slug, 'enterprise', '{}', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": PLATFORM_TENANT_ID, "slug": f"platform-{PLATFORM_TENANT_ID[:8]}"},
            )
            # Property tenant (for property admin)
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, 'Test Property', :slug, 'basic', '{}', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": PROPERTY_TENANT_ID, "slug": f"prop-{PROPERTY_TENANT_ID[:8]}"},
            )
            # Super admin user
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{PLATFORM_TENANT_ID}'"))
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'SUPER_ADMIN', true, true, now(), now())"
                ),
                {"id": sa_id, "tid": PLATFORM_TENANT_ID, "email": SUPER_ADMIN_EMAIL, "pw": sa_hash},
            )
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{PROPERTY_TENANT_ID}'"))
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'PROPERTY_ADMIN', true, true, now(), now())"
                ),
                {"id": pa_id, "tid": PROPERTY_TENANT_ID, "email": PROPERTY_ADMIN_EMAIL, "pw": pa_hash},
            )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        sa_login = await c.post(
            "/api/v1/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD, "tenant_id": PLATFORM_TENANT_ID},
        )
        assert sa_login.status_code == 200, f"SA login failed: {sa_login.text}"
        ADMIN_TOKEN = sa_login.json()["access_token"]

        pa_login = await c.post(
            "/api/v1/auth/login",
            json={"email": PROPERTY_ADMIN_EMAIL, "password": PROPERTY_ADMIN_PASSWORD, "tenant_id": PROPERTY_TENANT_ID},
        )
        assert pa_login.status_code == 200
        PROPERTY_ADMIN_TOKEN = pa_login.json()["access_token"]

    yield

    async with async_session() as db:
        for tid in [PLATFORM_TENANT_ID, PROPERTY_TENANT_ID]:
            async with db.begin():
                await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tid}'"))
                await db.execute(text("DELETE FROM users WHERE tenant_id = :tid"), {"tid": tid})
        async with db.begin():
            await db.execute(
                text("DELETE FROM tenants WHERE id IN (:p, :q)"),
                {"p": PLATFORM_TENANT_ID, "q": PROPERTY_TENANT_ID},
            )
        # Also clean up any tenants created during tests
        async with db.begin():
            await db.execute(
                text("DELETE FROM tenants WHERE slug LIKE 'test-created-%'")
            )
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_super_admin_can_list_tenants(client):
    resp = await client.get(
        "/api/v1/admin/tenants/",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_super_admin_can_create_tenant(client):
    slug = f"test-created-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/admin/tenants/",
        json={"name": "New Property", "slug": slug, "subscription_tier": "pro"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Property"
    assert data["subscription_tier"] == "pro"


async def test_super_admin_can_update_tenant(client):
    slug = f"test-created-{uuid.uuid4().hex[:8]}"
    create = await client.post(
        "/api/v1/admin/tenants/",
        json={"name": "Update Me", "slug": slug},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    tenant_id = create.json()["id"]

    resp = await client.put(
        f"/api/v1/admin/tenants/{tenant_id}",
        json={"subscription_tier": "enterprise"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["subscription_tier"] == "enterprise"


async def test_super_admin_can_get_stats(client):
    resp = await client.get(
        "/api/v1/admin/stats/",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 200
    assert "total_tenants" in resp.json()


async def test_duplicate_slug_returns_409(client):
    slug = f"test-created-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/v1/admin/tenants/",
        json={"name": "First", "slug": slug},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    resp = await client.post(
        "/api/v1/admin/tenants/",
        json={"name": "Second", "slug": slug},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 409


async def test_property_admin_cannot_access_admin_endpoints(client):
    resp = await client.post(
        "/api/v1/admin/tenants/",
        json={"name": "Blocked", "slug": f"blocked-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {PROPERTY_ADMIN_TOKEN}"},
    )
    assert resp.status_code == 403


async def test_update_nonexistent_tenant_returns_404(client):
    resp = await client.put(
        f"/api/v1/admin/tenants/{uuid.uuid4()}",
        json={"name": "Ghost"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/integration/test_admin_endpoints.py -v --tb=short
```
Expected: `7 passed`

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -q --tb=short 2>&1 | tail -10
```
Expected: 0 failures (86+ passed)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_admin_endpoints.py
git commit -m "test(integration): add admin endpoints integration tests"
```

---

## Chunk 3: Background Jobs

### Task 7: Install ARQ + `notifications.retry_count` migration

**Files:**
- Modify: `pyproject.toml` (add `arq`)
- Modify: `app/models/notification.py` (add `retry_count`)
- Create: `alembic/versions/xxxx_add_retry_count.py` (generated)

- [ ] **Step 1: Install ARQ**

```bash
uv add arq
```
Expected: `arq` added to `pyproject.toml` and `uv.lock`.

- [ ] **Step 2: Add `retry_count` to `Notification` model**

In `app/models/notification.py`, add after the `sent_at` column:

```python
    retry_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
```

- [ ] **Step 3: Generate migration**

```bash
uv run alembic revision --autogenerate -m "add retry_count to notifications"
```
Expected: new file in `alembic/versions/`.

- [ ] **Step 4: Review generated migration**

Open the generated file. Confirm it adds `retry_count INTEGER NOT NULL DEFAULT 0` to the `notifications` table. If autogenerate added unexpected changes, revert them — only `retry_count` should appear.

- [ ] **Step 5: Apply migration**

```bash
uv run alembic upgrade head
```
Expected: `Running upgrade ... add retry_count to notifications`

- [ ] **Step 6: Verify**

```bash
docker exec -it habitare-db-1 psql -U habitare_app -d habitare -c "\d notifications" | grep retry_count
```
Expected: `retry_count | integer | not null | default 0`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock app/models/notification.py alembic/versions/
git commit -m "feat(jobs): install arq, add retry_count column to notifications"
```

---

### Task 8: `retry_failed_notifications` job

**Files:**
- Create: `app/jobs/__init__.py`
- Create: `app/jobs/retry_notifications.py`

**Codebase context:** `NotificationService._send_email()` is private but its logic is inline and simple. The retry job replicates the send logic directly — it does NOT call `NotificationService` (which expects a `db` session passed at init time and is designed for the request lifecycle). Instead, the job uses raw httpx + SQLAlchemy directly, following the same pattern as `_send_email`.

The `notifications` table has RLS. The job groups by `tenant_id` and sets `SET LOCAL` per group inside a transaction. `Notification` model fields: `id`, `tenant_id`, `visit_id`, `channel`, `recipient_id`, `status`, `payload` (JSONB with `{"to": email, "visitor_name": name}`), `sent_at`, `retry_count`, `created_at`.

- [ ] **Step 1: Create `app/jobs/__init__.py`**

```python
# app/jobs/__init__.py
```
(empty file)

- [ ] **Step 2: Create `app/jobs/retry_notifications.py`**

```python
"""ARQ job: retry failed email notifications."""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import async_session
from app.models.notification import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_WINDOW_HOURS = 24


async def retry_failed_notifications(ctx: dict) -> None:
    """Retry FAILED email notifications, grouped by tenant_id to satisfy RLS.

    Skips notifications with retry_count >= MAX_RETRIES or older than RETRY_WINDOW_HOURS.
    """
    async with async_session() as db:
        # Fetch distinct tenant_ids with retryable failures (no RLS needed for this query
        # because we're filtering by status/retry_count across all tenants — use a
        # superuser-exempt approach: set an impossible tenant first, then query without filter,
        # then iterate per tenant with proper SET LOCAL).
        #
        # Simpler: fetch all retryable notifications without RLS by temporarily bypassing it.
        # The habitare_app role is non-superuser so we group by tenant_id and process per-tenant.
        async with db.begin():
            # Get retryable tenant_ids without RLS (notifications table does have RLS,
            # so we query for distinct tenant_ids via information we can access: since this
            # worker has no RLS context, the query will return empty. Instead, we fetch
            # tenant_ids from the tenants table (no RLS) and loop.
            from app.models.tenant import Tenant
            tenant_result = await db.execute(select(Tenant.id))
            tenant_ids = [row[0] for row in tenant_result.fetchall()]

    for tenant_id in tenant_ids:
        await _retry_for_tenant(tenant_id)


async def _retry_for_tenant(tenant_id) -> None:
    """Process retryable notifications for a single tenant."""
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))

            result = await db.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.channel == NotificationChannel.EMAIL,
                    Notification.status == NotificationStatus.FAILED,
                    Notification.retry_count < MAX_RETRIES,
                    text(f"created_at > now() - interval '{RETRY_WINDOW_HOURS} hours'"),
                )
            )
            notifications = result.scalars().all()

            for notif in notifications:
                email_to = notif.payload.get("to")
                visitor_name = notif.payload.get("visitor_name", "visitor")

                if not email_to:
                    notif.retry_count += 1
                    continue

                try:
                    if not getattr(settings, "sendgrid_api_key", None):
                        raise ValueError("HABITARE_SENDGRID_API_KEY not configured")
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://api.sendgrid.com/v3/mail/send",
                            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                            json={
                                "personalizations": [{"to": [{"email": email_to}]}],
                                "from": {"email": getattr(settings, "from_email", "noreply@habitare.com")},
                                "subject": f"Visitor {visitor_name} has arrived",
                                "content": [{"type": "text/plain", "value": f"{visitor_name} has checked in."}],
                            },
                            timeout=10.0,
                        )
                        resp.raise_for_status()
                    notif.status = NotificationStatus.SENT
                    notif.sent_at = datetime.now(timezone.utc)
                    logger.info("Retried notification %s: SENT", notif.id)
                except Exception as exc:
                    notif.retry_count += 1
                    logger.warning("Retry failed for notification %s (attempt %d): %s", notif.id, notif.retry_count, exc)
```

- [ ] **Step 3: Verify import**

```bash
uv run python -c "from app.jobs.retry_notifications import retry_failed_notifications; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/jobs/__init__.py app/jobs/retry_notifications.py
git commit -m "feat(jobs): add retry_failed_notifications ARQ job"
```

---

### Task 9: `cleanup_expired_tokens` job + ARQ worker entry point

**Files:**
- Create: `app/jobs/cleanup_tokens.py`
- Create: `app/worker.py`

**Codebase context:** `refresh_tokens` table has NO RLS — the cleanup job can query it freely without `SET LOCAL`. `settings.redis_url` is already in `app/core/config.py`. ARQ `WorkerSettings` uses `redis_settings` (an `arq.connections.RedisSettings` object, created from the URL) and `cron_jobs` (list of `arq.cron` objects).

- [ ] **Step 1: Create `app/jobs/cleanup_tokens.py`**

```python
"""ARQ job: delete expired and revoked refresh tokens."""
import logging
from sqlalchemy import text
from app.core.database import async_session

logger = logging.getLogger(__name__)


async def cleanup_expired_tokens(ctx: dict) -> None:
    """Delete refresh tokens that are expired (>30d) or revoked (>7d).

    refresh_tokens has no RLS — no SET LOCAL needed.
    """
    async with async_session() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    "DELETE FROM refresh_tokens "
                    "WHERE expires_at < now() - interval '30 days' "
                    "   OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days') "
                    "RETURNING id"
                )
            )
            deleted = len(result.fetchall())
            logger.info("cleanup_expired_tokens: deleted %d tokens", deleted)
```

- [ ] **Step 2: Create `app/worker.py`**

```python
"""ARQ worker entry point.

Run with: uv run arq app.worker.WorkerSettings
"""
from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.jobs.cleanup_tokens import cleanup_expired_tokens
from app.jobs.retry_notifications import retry_failed_notifications


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [
        retry_failed_notifications,
        cleanup_expired_tokens,
    ]

    cron_jobs = [
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(cleanup_expired_tokens, hour=3, minute=0),
    ]
```

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "from app.worker import WorkerSettings; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/jobs/cleanup_tokens.py app/worker.py
git commit -m "feat(jobs): add cleanup_expired_tokens job and ARQ worker entry point"
```

---

### Task 10: Unit tests for job functions

**Files:**
- Create: `tests/unit/test_jobs.py`

**Codebase context:** Job functions take a `ctx: dict` (ARQ context) as first argument — pass `{}` in tests. Both functions use `async_session()` from `app.core.database` and run against the real test DB. The `notifications` table requires RLS context; seed data must use `SET LOCAL`. The `refresh_tokens` table has no RLS.

- [ ] **Step 1: Write the test file**

```python
# tests/unit/test_jobs.py
"""Unit tests for ARQ background job functions."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.database import async_session, engine
from app.jobs.cleanup_tokens import cleanup_expired_tokens
from app.jobs.retry_notifications import retry_failed_notifications
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.models.token import RefreshToken

TENANT_ID = str(uuid.uuid4())
VISIT_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())


@pytest_asyncio.fixture(autouse=True)
async def setup_tenant():
    """Seed test tenant, user, visitor, and visit for FK constraints."""
    from app.core.security import hash_password
    visitor_id = str(uuid.uuid4())

    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, 'Jobs Test Tenant', :slug, 'basic', '{}', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": TENANT_ID, "slug": f"jobs-{TENANT_ID[:8]}"},
            )
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            # Seed user (required as FK for refresh_tokens)
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now()) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": USER_ID,
                    "tid": TENANT_ID,
                    "email": f"jobs-user-{TENANT_ID[:8]}@test.com",
                    "pw": hash_password("pw"),
                },
            )
            # Seed visitor + visit (required as FK for notifications)
            await db.execute(
                text(
                    "INSERT INTO visitors (id, tenant_id, name, created_at, updated_at) "
                    "VALUES (:id, :tid, 'Test Visitor', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": visitor_id, "tid": TENANT_ID},
            )
            await db.execute(
                text(
                    "INSERT INTO visits (id, tenant_id, visitor_id, purpose, status, created_at, updated_at) "
                    "VALUES (:id, :tid, :vid, 'Test', 'scheduled', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": VISIT_ID, "tid": TENANT_ID, "vid": visitor_id},
            )

    yield

    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            for table in ["notifications", "qr_codes", "invitations", "visits", "visitors", "users"]:
                await db.execute(text(f"DELETE FROM {table} WHERE tenant_id = '{TENANT_ID}'"))
        async with db.begin():
            await db.execute(text("DELETE FROM refresh_tokens WHERE tenant_id = :tid"), {"tid": TENANT_ID})
        async with db.begin():
            await db.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": TENANT_ID})
    await engine.dispose()


async def _seed_notification(retry_count: int = 0, created_hours_ago: int = 1) -> uuid.UUID:
    """Seed a FAILED email notification."""
    notif_id = uuid.uuid4()
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            await db.execute(
                text(
                    "INSERT INTO notifications (id, tenant_id, visit_id, channel, status, payload, retry_count, created_at, updated_at) "
                    "VALUES (:id, :tid, :vid, 'email', 'failed', :payload, :rc, "
                    "now() - :hours * interval '1 hour', now())"
                ),
                {
                    "id": str(notif_id),
                    "tid": TENANT_ID,
                    "vid": VISIT_ID,
                    "payload": '{"to": "host@example.com", "visitor_name": "Test"}',
                    "rc": retry_count,
                    "hours": created_hours_ago,
                },
            )
    return notif_id


async def _get_notification(notif_id: uuid.UUID) -> Notification | None:
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            result = await db.execute(select(Notification).where(Notification.id == notif_id))
            return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_retry_job_increments_retry_count_on_failure():
    """With no SendGrid key, retry should increment retry_count and keep FAILED."""
    notif_id = await _seed_notification(retry_count=0)
    await retry_failed_notifications({})
    notif = await _get_notification(notif_id)
    assert notif is not None
    # No SendGrid key configured in test env — expect retry_count incremented
    assert notif.retry_count == 1
    assert notif.status == NotificationStatus.FAILED


@pytest.mark.asyncio
async def test_retry_job_skips_max_retries():
    """Notification with retry_count >= 3 should not be touched."""
    notif_id = await _seed_notification(retry_count=3)
    await retry_failed_notifications({})
    notif = await _get_notification(notif_id)
    assert notif.retry_count == 3  # unchanged


@pytest.mark.asyncio
async def test_retry_job_skips_old_notifications():
    """Notification older than 24h should not be retried."""
    notif_id = await _seed_notification(retry_count=0, created_hours_ago=25)
    await retry_failed_notifications({})
    notif = await _get_notification(notif_id)
    assert notif.retry_count == 0  # unchanged


@pytest.mark.asyncio
async def test_cleanup_deletes_long_expired_token():
    """Token expired >30 days ago should be deleted."""
    token_id = uuid.uuid4()
    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, tenant_id, token_hash, expires_at, created_at) "
                    "VALUES (:id, :uid, :tid, :hash, now() - interval '31 days', now())"
                ),
                {"id": str(token_id), "uid": USER_ID, "tid": TENANT_ID, "hash": f"expired-{token_id.hex}"},
            )

    await cleanup_expired_tokens({})

    async with async_session() as db:
        async with db.begin():
            result = await db.execute(select(RefreshToken).where(RefreshToken.id == token_id))
            assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_valid_token():
    """Active token not yet expired should NOT be deleted."""
    token_id = uuid.uuid4()
    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, tenant_id, token_hash, expires_at, created_at) "
                    "VALUES (:id, :uid, :tid, :hash, now() + interval '14 days', now())"
                ),
                {"id": str(token_id), "uid": USER_ID, "tid": TENANT_ID, "hash": f"valid-{token_id.hex}"},
            )

    await cleanup_expired_tokens({})

    async with async_session() as db:
        async with db.begin():
            result = await db.execute(select(RefreshToken).where(RefreshToken.id == token_id))
            assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_cleanup_deletes_old_revoked_token():
    """Token revoked >7 days ago should be deleted even if not expired."""
    token_id = uuid.uuid4()
    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, tenant_id, token_hash, expires_at, revoked_at, created_at) "
                    "VALUES (:id, :uid, :tid, :hash, now() + interval '14 days', now() - interval '8 days', now())"
                ),
                {"id": str(token_id), "uid": USER_ID, "tid": TENANT_ID, "hash": f"revoked-{token_id.hex}"},
            )

    await cleanup_expired_tokens({})

    async with async_session() as db:
        async with db.begin():
            result = await db.execute(select(RefreshToken).where(RefreshToken.id == token_id))
            assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/unit/test_jobs.py -v --tb=short
```
Expected: `6 passed`

- [ ] **Step 3: Run full suite to confirm no regressions**

```bash
uv run pytest tests/ -q --tb=short 2>&1 | tail -10
```
Expected: 0 failures

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_jobs.py
git commit -m "test(unit): add ARQ job unit tests"
```

---

### Task 11: Final check + push + PR

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: 0 failures, 100+ passed

- [ ] **Step 2: Verify OpenAPI**

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8766 &
sleep 3
curl -s http://127.0.0.1:8766/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Routes:', len(d['paths']))"
kill %1 2>/dev/null || true
```
Expected: `Routes: 29+`

- [ ] **Step 3: Push branch**

```bash
git push -u origin feat/phase-4-rbac-jobs
```

- [ ] **Step 4: Create PR**

```bash
/opt/homebrew/bin/gh pr create \
  --title "feat(phase-4): RBAC, user management & background jobs" \
  --body "## Summary

- Add \`require_role()\` dependency factory; guard \`/admin/*\` (SUPER_ADMIN) and user management (PROPERTY_ADMIN+)
- Implement \`PUT /users/me\`, \`GET /users/\`, \`POST /users/\` (returns one-time temp password), \`PUT /users/{id}\`
- Implement \`POST /admin/tenants/\` and \`PUT /admin/tenants/{id}\` (were 501 stubs)
- Add ARQ worker with \`retry_failed_notifications\` (every 5 min) and \`cleanup_expired_tokens\` (nightly 03:00)
- Add \`notifications.retry_count\` column + migration

## Test plan
- [ ] \`uv run pytest tests/unit/test_require_role.py tests/unit/test_jobs.py -v\`
- [ ] \`uv run pytest tests/integration/test_user_management.py tests/integration/test_admin_endpoints.py -v\`
- [ ] \`uv run pytest tests/ -q\` — 0 failures
- [ ] \`uv run alembic upgrade head\` on fresh DB
- [ ] \`uv run arq app.worker.WorkerSettings\` — worker starts without error

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Report PR URL.
