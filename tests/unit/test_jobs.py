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
