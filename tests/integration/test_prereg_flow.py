"""Pre-registration flow: create visit with scheduled_at → pass link → QR scan → checked in."""
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

TENANT_ID = str(uuid.uuid4())
USER_EMAIL = f"testuser-{TENANT_ID[:8]}@example.com"
USER_PASSWORD = "test-password-123"
ACCESS_TOKEN = None
# 30 minutes in the future: TIME_BOUNDED QR valid_from = now-60min, valid_until = now+90min
# So the QR is valid at scan time (now). Do not use values > 60min or < -1min.
FUTURE_VISIT = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()


@pytest_asyncio.fixture(autouse=True)
async def setup_tenant():
    """Insert test tenant and user; delete all tenant data in FK-safe order on teardown.

    Disposes the engine before and after to prevent asyncpg event-loop conflicts
    when the full test suite runs (each test gets a fresh event loop in STRICT mode).
    """
    global ACCESS_TOKEN
    await engine.dispose()
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO tenants (id, name, slug, subscription_tier)
                    VALUES (:id, 'PreReg Tenant', :slug, 'basic')
                    ON CONFLICT DO NOTHING
                """),
                {"id": TENANT_ID, "slug": f"prereg-{TENANT_ID[:8]}"},
            )

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(USER_PASSWORD)
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'")
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, password_hash, role, "
                    "is_active, email_verified, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, :pw, 'TENANT_USER', true, true, now(), now())"
                ),
                {"id": user_id, "tid": TENANT_ID, "email": USER_EMAIL, "pw": pw_hash},
            )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD, "tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        ACCESS_TOKEN = resp.json()["access_token"]

    yield
    async with async_session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
            for table in ["notifications", "invitations", "qr_codes", "visits", "visitors", "users"]:
                await session.execute(text(f"DELETE FROM {table} WHERE tenant_id = '{TENANT_ID}'"))
            await session.execute(text(f"DELETE FROM tenants WHERE id = '{TENANT_ID}'"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_prereg_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create visitor with email
        resp = await client.post(
            "/api/v1/visitors/",
            json={"name": "Pre-Reg Guest", "email": "guest@example.com"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        )
        assert resp.status_code == 201
        visitor_id = resp.json()["id"]

        # 2. Create scheduled visit
        resp = await client.post(
            "/api/v1/visits/",
            json={"visitor_id": visitor_id, "purpose": "Business Meeting", "scheduled_at": FUTURE_VISIT},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        )
        assert resp.status_code == 201
        visit_id = resp.json()["id"]

        # 3. Verify TIME_BOUNDED QR was auto-created — set RLS context for the query
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
                result = await session.execute(
                    select(QRCode).where(QRCode.visit_id == uuid.UUID(visit_id))
                )
                qr = result.scalar_one()
                assert qr.type.value == "time_bounded"
                code = str(qr.code)

        # 4. Verify invitation (pass link) was auto-created
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
                result = await session.execute(
                    select(Invitation).where(Invitation.visit_id == uuid.UUID(visit_id))
                )
                inv = result.scalar_one()
                token = inv.token
                inv_id = inv.id

        # 5. Visitor opens pass link — marks invitation as VIEWED
        resp = await client.get(f"/api/v1/pass/{token}")
        assert resp.status_code == 200
        assert resp.json()["visitor_name"] == "Pre-Reg Guest"
        assert "qr_code_url" in resp.json()

        # Verify invitation status transitioned to VIEWED
        async with async_session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL app.current_tenant_id = '{TENANT_ID}'"))
                result = await session.execute(
                    select(Invitation).where(Invitation.id == inv_id)
                )
                updated_inv = result.scalar_one()
                assert updated_inv.status.value == "viewed"

        # 6. Staff scans QR → check-in
        resp = await client.get(f"/api/v1/qr/{code}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
        assert resp.status_code == 200

        # 7. Verify CHECKED_IN
        resp = await client.get(f"/api/v1/visits/{visit_id}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"

        # 8. Check out
        resp = await client.post(f"/api/v1/visits/{visit_id}/check-out", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_out"
