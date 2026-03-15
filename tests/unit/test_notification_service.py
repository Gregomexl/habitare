import uuid
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.notification_service import NotificationService


def _make_db_mock():
    """Create an AsyncMock db with begin() as a proper async context manager."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()

    @asynccontextmanager
    async def _begin():
        yield

    db.begin = _begin
    return db


@pytest.mark.asyncio
async def test_notify_skips_email_when_no_host():
    """No email sent when host_id is None."""
    db = _make_db_mock()
    service = NotificationService(db)

    with patch.object(service, "_send_email", new_callable=AsyncMock) as mock_email:
        with patch.object(service, "_broadcast_ws", new_callable=AsyncMock):
            await service.notify_checkin(
                tenant_id=uuid.uuid4(),
                visit_id=uuid.uuid4(),
                host_id=None,
                visitor_name="Jane",
                host_email=None,
            )
        mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_notify_calls_email_when_host_present():
    """Email dispatched when host_id and host_email are set."""
    db = _make_db_mock()
    service = NotificationService(db)

    with patch.object(service, "_send_email", new_callable=AsyncMock) as mock_email:
        with patch.object(service, "_broadcast_ws", new_callable=AsyncMock):
            await service.notify_checkin(
                tenant_id=uuid.uuid4(),
                visit_id=uuid.uuid4(),
                host_id=uuid.uuid4(),
                visitor_name="Jane",
                host_email="host@example.com",
            )
        mock_email.assert_called_once()
