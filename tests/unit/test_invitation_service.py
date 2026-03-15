import uuid
from datetime import datetime, timedelta, timezone
import pytest
from app.services.invitation_service import InvitationService


def test_generate_token_is_string():
    tid = uuid.uuid4()
    token = InvitationService.generate_token(tid)
    assert isinstance(token, str)
    assert token.startswith(str(tid) + ".")
    assert len(token) > 40


def test_generate_token_unique():
    tid = uuid.uuid4()
    t1 = InvitationService.generate_token(tid)
    t2 = InvitationService.generate_token(tid)
    assert t1 != t2


def test_build_pass_url():
    token = "abc123"
    url = InvitationService.build_pass_url(token, base_url="https://app.habitare.com")
    assert url == "https://app.habitare.com/pass/abc123"


def test_is_valid_returns_true_for_pending_unexpired():
    from types import SimpleNamespace
    from datetime import timedelta
    from app.models.invitation import InvitationStatus
    inv = SimpleNamespace(
        status=InvitationStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert InvitationService(db=None).is_valid(inv) is True


def test_is_valid_returns_false_for_expired_status():
    from types import SimpleNamespace
    from datetime import timedelta
    from app.models.invitation import InvitationStatus
    inv = SimpleNamespace(
        status=InvitationStatus.EXPIRED,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert InvitationService(db=None).is_valid(inv) is False


def test_is_valid_returns_false_when_past_expires_at():
    from types import SimpleNamespace
    from datetime import timedelta
    from app.models.invitation import InvitationStatus
    inv = SimpleNamespace(
        status=InvitationStatus.PENDING,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert InvitationService(db=None).is_valid(inv) is False


@pytest.mark.asyncio
async def test_mark_viewed_transitions_pending_to_viewed():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.models.invitation import InvitationStatus
    db = MagicMock()
    db.flush = AsyncMock()
    inv = SimpleNamespace(status=InvitationStatus.PENDING)
    service = InvitationService(db)
    result = await service.mark_viewed(inv)
    assert result.status == InvitationStatus.VIEWED


@pytest.mark.asyncio
async def test_mark_viewed_does_not_change_already_viewed():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.models.invitation import InvitationStatus
    db = MagicMock()
    db.flush = AsyncMock()
    inv = SimpleNamespace(status=InvitationStatus.VIEWED)
    service = InvitationService(db)
    result = await service.mark_viewed(inv)
    assert result.status == InvitationStatus.VIEWED  # unchanged


@pytest.mark.asyncio
async def test_revoke_sets_expired():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.models.invitation import InvitationStatus
    db = MagicMock()
    db.flush = AsyncMock()
    inv = SimpleNamespace(status=InvitationStatus.PENDING)
    service = InvitationService(db)
    result = await service.revoke(inv)
    assert result.status == InvitationStatus.EXPIRED
