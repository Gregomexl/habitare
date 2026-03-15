"""Verify RLS prevents cross-tenant QR scan and data access."""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, select
from app.main import app
from app.core.database import async_session, engine
from app.core.security import hash_password
from app.models.qr_code import QRCode
from app.models.invitation import Invitation

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())
USER_A_EMAIL = f"usera-{TENANT_A[:8]}@example.com"
USER_B_EMAIL = f"userb-{TENANT_B[:8]}@example.com"
USER_A_PASSWORD = "password-a-123"
USER_B_PASSWORD = "password-b-123"
ACCESS_TOKEN_A = None
ACCESS_TOKEN_B = None


@pytest_asyncio.fixture(autouse=True)
async def setup_tenants():
    """Insert both test tenants and users; delete all their data in FK-safe order on teardown.

    Disposes the engine after each test to prevent asyncpg event-loop conflicts
    across test functions (each test gets a fresh event loop in STRICT mode).
    """
    global ACCESS_TOKEN_A, ACCESS_TOKEN_B
    await engine.dispose()
    async with async_session() as session:
        async with session.begin():
            for tid, name, slug in [
                (TENANT_A, "Tenant A", f"a-{TENANT_A[:8]}"),
                (TENANT_B, "Tenant B", f"b-{TENANT_B[:8]}"),
            ]:
                await session.execute(
                    text("""
                        INSERT INTO tenants (id, name, slug, subscription_tier)
                        VALUES (:id, :name, :slug, 'basic') ON CONFLICT DO NOTHING
                    """),
                    {"id": tid, "name": name, "slug": slug},
                )

    # Insert user for Tenant A
    user_a_id = str(uuid.uuid4())
    pw_hash_a = hash_password(USER_A_PASSWORD)
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_A}'")
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now())"
                ),
                {"id": user_a_id, "tid": TENANT_A, "email": USER_A_EMAIL, "pw": pw_hash_a},
            )

    # Insert user for Tenant B
    user_b_id = str(uuid.uuid4())
    pw_hash_b = hash_password(USER_B_PASSWORD)
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_B}'")
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now())"
                ),
                {"id": user_b_id, "tid": TENANT_B, "email": USER_B_EMAIL, "pw": pw_hash_b},
            )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": USER_A_EMAIL, "password": USER_A_PASSWORD, "tenant_id": TENANT_A},
        )
        assert resp.status_code == 200, f"Login A failed: {resp.text}"
        ACCESS_TOKEN_A = resp.json()["access_token"]

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": USER_B_EMAIL, "password": USER_B_PASSWORD, "tenant_id": TENANT_B},
        )
        assert resp.status_code == 200, f"Login B failed: {resp.text}"
        ACCESS_TOKEN_B = resp.json()["access_token"]

    yield
    for tid in [TENANT_A, TENANT_B]:
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{tid}'"))
                for table in ["notifications", "invitations", "qr_codes", "visits", "visitors", "users"]:
                    await session.execute(text(f"DELETE FROM {table} WHERE tenant_id = '{tid}'"))
    async with async_session() as session:
        async with session.begin():
            for tid in [TENANT_A, TENANT_B]:
                await session.execute(text(f"DELETE FROM tenants WHERE id = '{tid}'"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_b_cannot_scan_tenant_a_qr():
    """QR code from Tenant A must be invisible to Tenant B scanner."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create visitor + visit in Tenant A
        resp = await client.post(
            "/api/v1/visitors/",
            json={"name": "Tenant A Visitor"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_A}"},
        )
        assert resp.status_code == 201, f"Visitor creation failed: {resp.text}"
        visitor_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/visits/",
            json={"visitor_id": visitor_id, "purpose": "Test"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_A}"},
        )
        assert resp.status_code == 201, f"Visit creation failed: {resp.text}"
        visit_id = resp.json()["id"]

        # Get Tenant A's QR code — set RLS context so the query is authorized
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_A}'"))
                result = await session.execute(
                    select(QRCode).where(QRCode.visit_id == uuid.UUID(visit_id))
                )
                qr = result.scalar_one()
                code = str(qr.code)

        # Attempt to scan with Tenant B credentials → must fail
        resp = await client.get(
            f"/api/v1/qr/{code}",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_B}"},
        )
        assert resp.status_code == 404, (
            f"Tenant B should not see Tenant A's QR code. Got {resp.status_code}: {resp.text}"
        )


@pytest.mark.asyncio
async def test_tenant_b_cannot_list_tenant_a_visitors():
    """Visitors created in Tenant A must not appear in Tenant B's list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create visitor in Tenant A
        resp = await client.post(
            "/api/v1/visitors/",
            json={"name": "Secret Visitor A", "email": f"secret-{uuid.uuid4()}@a.com"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_A}"},
        )
        assert resp.status_code == 201, f"Visitor creation failed: {resp.text}"

        # List visitors as Tenant B
        resp = await client.get("/api/v1/visitors/", headers={"Authorization": f"Bearer {ACCESS_TOKEN_B}"})
        assert resp.status_code == 200
        names = [v["name"] for v in resp.json()]
        assert "Secret Visitor A" not in names


@pytest.mark.asyncio
async def test_expired_pass_token_returns_410():
    """An expired invitation token must return 410 Gone."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create visitor + visit in Tenant A to get a real invitation token
        resp = await client.post(
            "/api/v1/visitors/",
            json={"name": "Expired Token Visitor"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_A}"},
        )
        assert resp.status_code == 201
        visitor_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/visits/",
            json={"visitor_id": visitor_id, "purpose": "Expired Test"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN_A}"},
        )
        assert resp.status_code == 201
        visit_id = resp.json()["id"]

        # Fetch invitation and manually expire it in the DB
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_A}'"))
                result = await session.execute(
                    select(Invitation).where(Invitation.visit_id == uuid.UUID(visit_id))
                )
                inv = result.scalar_one()
                token = inv.token
                # Force expires_at to the past
                inv.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        # Call pass link with expired token → must return 410
        resp = await client.get(f"/api/v1/pass/{token}")
        assert resp.status_code == 410, (
            f"Expired pass token must return 410. Got {resp.status_code}: {resp.text}"
        )
