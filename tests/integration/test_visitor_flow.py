"""Full walk-in flow: create visitor → create visit → QR generated → scan → checked in."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, select
from app.main import app
from app.core.database import async_session
from app.models.qr_code import QRCode
from app.models.invitation import Invitation

TENANT_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-Id": TENANT_ID}


@pytest_asyncio.fixture(autouse=True)
async def setup_tenant():
    """Insert test tenant; delete all tenant data in FK-safe order on teardown."""
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO tenants (id, name, slug, subscription_tier)
                    VALUES (:id, 'Test Tenant', :slug, 'basic')
                    ON CONFLICT DO NOTHING
                """),
                {"id": TENANT_ID, "slug": f"test-{TENANT_ID[:8]}"},
            )
    yield
    async with async_session() as session:
        async with session.begin():
            # SET LOCAL so RLS allows deletes on tenant-scoped tables
            await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            for table in ["notifications", "invitations", "qr_codes", "visits", "visitors", "users"]:
                await session.execute(text(f"DELETE FROM {table} WHERE tenant_id = '{TENANT_ID}'"))
            # tenants table has no RLS (not tenant-scoped)
            await session.execute(text(f"DELETE FROM tenants WHERE id = '{TENANT_ID}'"))


@pytest.mark.asyncio
async def test_walk_in_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create visitor (omit email for walk-in)
        resp = await client.post(
            "/api/v1/visitors/",
            json={"name": "Walk-In Guest"},
            headers=HEADERS,
        )
        assert resp.status_code == 201
        visitor_id = resp.json()["id"]

        # 2. Create walk-in visit (no scheduled_at, no host_id)
        # This auto-creates a ONE_TIME QR code + invitation with pass link
        resp = await client.post(
            "/api/v1/visits/",
            json={"visitor_id": visitor_id, "purpose": "Delivery"},
            headers=HEADERS,
        )
        assert resp.status_code == 201
        visit_id = resp.json()["id"]
        assert resp.json()["status"] == "scheduled"

        # 3. Fetch QR code + invitation from DB (set RLS context so query is authorized)
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
                result = await session.execute(
                    select(QRCode).where(QRCode.visit_id == uuid.UUID(visit_id))
                )
                qr = result.scalar_one()
                assert qr.type.value == "one_time"
                code = str(qr.code)
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
                result = await session.execute(
                    select(Invitation).where(Invitation.visit_id == uuid.UUID(visit_id))
                )
                inv = result.scalar_one()
                token = inv.token

        # 4. Visitor opens pass link (walk-in staff shares on the spot)
        resp = await client.get(f"/api/v1/pass/{token}")
        assert resp.status_code == 200
        assert "qr_code_url" in resp.json()

        # 5. Scan the QR code (staff action)
        resp = await client.get(f"/api/v1/qr/{code}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["visit_id"] == visit_id

        # 6. Verify visit is now CHECKED_IN
        resp = await client.get(f"/api/v1/visits/{visit_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"

        # 7. Check out
        resp = await client.post(f"/api/v1/visits/{visit_id}/check-out", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_out"
