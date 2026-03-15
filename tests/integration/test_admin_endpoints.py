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
