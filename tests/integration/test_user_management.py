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
