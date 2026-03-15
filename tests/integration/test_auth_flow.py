# tests/integration/test_auth_flow.py
"""Integration test: full auth flow — login, /users/me, refresh, logout, revocation."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session, engine
from app.core.security import hash_password
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="module")

TENANT_ID = str(uuid.uuid4())
USER_EMAIL = f"staff-{uuid.uuid4().hex[:8]}@test.com"
USER_PASSWORD = "correct-horse-battery"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def seed_auth_data():
    """Insert a tenant and user directly; tear down after module."""
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(USER_PASSWORD)

    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, 'basic', '{}', now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"id": TENANT_ID, "name": "Auth Test Tenant", "slug": f"auth-test-{TENANT_ID[:8]}"},
            )
            # SET LOCAL so RLS allows the INSERT into users
            await db.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'")
            )
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now())"
                ),
                {"id": user_id, "tid": TENANT_ID, "email": USER_EMAIL, "pw": pw_hash},
            )

    yield

    async with async_session() as db:
        # Two separate transactions: first DELETE users (RLS requires SET LOCAL),
        # then DELETE tenants (no RLS — cannot share a transaction or SET LOCAL expires).
        async with db.begin():
            await db.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'")
            )
            await db.execute(
                text("DELETE FROM users WHERE email = :email"), {"email": USER_EMAIL}
            )
        async with db.begin():
            await db.execute(
                text("DELETE FROM tenants WHERE id = :id"), {"id": TENANT_ID}
            )
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_login_returns_token_pair(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.access_token_expire_minutes * 60


async def test_login_wrong_password_returns_401(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": "wrong", "tenant_id": TENANT_ID},
    )
    assert resp.status_code == 401


async def test_users_me_with_valid_token(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    access_token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == USER_EMAIL
    assert me["role"] == "tenant_user"


async def test_users_me_without_token_returns_401(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_refresh_returns_new_token_pair(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # new token issued


async def test_old_refresh_token_rejected_after_rotation(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    old_refresh = login.json()["refresh_token"]
    # Rotate
    await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    # Try old token again
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401


async def test_logout_revokes_refresh_token(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    tokens = login.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout.status_code == 204

    # Revoked token rejected
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


async def test_protected_endpoint_with_valid_token(client):
    """Visitors endpoint respects JWT tenant scope."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    access_token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/visitors/",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_protected_endpoint_without_token_returns_401(client):
    resp = await client.get("/api/v1/visitors/")
    assert resp.status_code == 401


async def test_cross_tenant_token_cannot_see_other_tenant_data(client):
    """JWT scoped to tenant A must not return tenant B visitors (RLS enforcement)."""
    # Seed a second tenant with its own user and visitor
    tenant_b_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    user_b_email = f"staff-b-{uuid.uuid4().hex[:8]}@test.com"
    visitor_b_id = str(uuid.uuid4())

    async with async_session() as db:
        async with db.begin():
            await db.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, subscription_tier, settings, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, 'basic', '{}', now(), now())"
                ),
                {"id": tenant_b_id, "name": "Tenant B", "slug": f"tenant-b-{tenant_b_id[:8]}"},
            )
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_b_id}'"))
            await db.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now())"
                ),
                {
                    "id": user_b_id,
                    "tid": tenant_b_id,
                    "email": user_b_email,
                    "pw": hash_password("password-b"),
                },
            )
            await db.execute(
                text(
                    "INSERT INTO visitors (id, tenant_id, name, created_at, updated_at) "
                    "VALUES (:id, :tid, 'Tenant B Visitor', now(), now())"
                ),
                {"id": visitor_b_id, "tid": tenant_b_id},
            )

    # Login as tenant A user
    login_a = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
    )
    token_a = login_a.json()["access_token"]

    # Tenant A token → tenant A visitors list (should not contain tenant B visitor)
    resp = await client.get(
        "/api/v1/visitors/",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    visitor_ids = [v["id"] for v in resp.json()]
    assert visitor_b_id not in visitor_ids

    # Cleanup tenant B
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_b_id}'"))
            await db.execute(
                text("DELETE FROM visitors WHERE tenant_id = :tid"), {"tid": tenant_b_id}
            )
            await db.execute(
                text("DELETE FROM users WHERE tenant_id = :tid"), {"tid": tenant_b_id}
            )
        async with db.begin():
            await db.execute(
                text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_b_id}
            )
