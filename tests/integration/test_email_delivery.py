"""Integration test: email delivery via Resend API."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


@pytest.mark.asyncio
async def test_send_email_calls_resend_api(monkeypatch):
    """_send_email should POST to Resend API with correct shape."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "from_email", "noreply@test.com")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    posted_json = {}

    async def mock_post(url, **kwargs):
        posted_json.update(kwargs.get("json", {}))
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        import uuid
        from app.services.notification_service import NotificationService
        from unittest.mock import MagicMock as MM
        db = MM()
        db.add = MM()
        db.flush = AsyncMock()
        db.begin = MM()
        db.begin.return_value.__aenter__ = AsyncMock(return_value=db)
        db.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        svc = NotificationService(db)
        await svc._send_email(
            tenant_id=uuid.uuid4(),
            visit_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
            host_email="host@example.com",
            visitor_name="Alice",
        )
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://api.resend.com/emails"
        headers = call_args[1]["headers"]
        assert "Bearer re_test_key" in headers["Authorization"]
        body = call_args[1]["json"]
        assert body["to"] == ["host@example.com"]
        assert body["from"] == "noreply@test.com"


@pytest.mark.asyncio
async def test_send_email_skipped_when_disabled(monkeypatch):
    """_send_email should not make any HTTP call when email_enabled=False."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_enabled", False)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        import uuid
        from app.services.notification_service import NotificationService
        from unittest.mock import MagicMock as MM
        db = MM()
        db.add = MM()
        db.flush = AsyncMock()
        db.begin = MM()
        db.begin.return_value.__aenter__ = AsyncMock(return_value=db)
        db.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        svc = NotificationService(db)
        await svc._send_email(
            tenant_id=uuid.uuid4(),
            visit_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
            host_email="host@example.com",
            visitor_name="Alice",
        )
        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_handles_missing_host_email_gracefully(monkeypatch):
    """_send_email called with no host_email should not raise — handled in service."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    import uuid
    from app.services.notification_service import NotificationService
    from unittest.mock import AsyncMock, MagicMock as MM, patch

    db = MM()
    db.add = MM()
    db.flush = AsyncMock()
    db.begin = MM()
    db.begin.return_value.__aenter__ = AsyncMock(return_value=db)
    db.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    db.execute = AsyncMock()

    svc = NotificationService(db)
    # Should not raise even if host_email is empty string
    try:
        await svc._send_email(
            tenant_id=uuid.uuid4(),
            visit_id=uuid.uuid4(),
            host_id=uuid.uuid4(),
            host_email="",  # missing / empty
            visitor_name="Bob",
        )
    except Exception as exc:
        pytest.fail(f"_send_email raised unexpectedly: {exc}")
