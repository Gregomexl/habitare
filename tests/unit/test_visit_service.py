import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import text
from app.core.database import async_session
from app.models.visit import Visit, VisitStatus
from app.models.visitor import Visitor
from app.services.visit_service import VisitService, VisitStateError


@pytest_asyncio.fixture
async def db_session_with_tenant(manage_engine):
    tenant_id = uuid.uuid4()
    async with async_session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
            yield session, tenant_id


@pytest.mark.asyncio
async def test_check_in_transitions_to_checked_in(db_session_with_tenant):
    session, tenant_id = db_session_with_tenant
    visitor = Visitor(tenant_id=tenant_id, name="Test Visitor")
    session.add(visitor)
    await session.flush()

    visit = Visit(
        tenant_id=tenant_id,
        visitor_id=visitor.id,
        purpose="Meeting",
        status=VisitStatus.SCHEDULED,
    )
    session.add(visit)
    await session.flush()

    service = VisitService(session)
    updated = await service.check_in(visit.id)
    assert updated.status == VisitStatus.CHECKED_IN
    assert updated.checked_in_at is not None


@pytest.mark.asyncio
async def test_check_in_already_checked_in_raises(db_session_with_tenant):
    session, tenant_id = db_session_with_tenant
    visitor = Visitor(tenant_id=tenant_id, name="Test")
    session.add(visitor)
    await session.flush()

    visit = Visit(
        tenant_id=tenant_id,
        visitor_id=visitor.id,
        purpose="Meeting",
        status=VisitStatus.CHECKED_IN,
        checked_in_at=datetime.now(timezone.utc),
    )
    session.add(visit)
    await session.flush()

    service = VisitService(session)
    with pytest.raises(VisitStateError):
        await service.check_in(visit.id)


@pytest.mark.asyncio
async def test_check_out_transitions_to_checked_out(db_session_with_tenant):
    session, tenant_id = db_session_with_tenant
    visitor = Visitor(tenant_id=tenant_id, name="Test")
    session.add(visitor)
    await session.flush()

    visit = Visit(
        tenant_id=tenant_id,
        visitor_id=visitor.id,
        purpose="Meeting",
        status=VisitStatus.CHECKED_IN,
        checked_in_at=datetime.now(timezone.utc),
    )
    session.add(visit)
    await session.flush()

    service = VisitService(session)
    updated = await service.check_out(visit.id)
    assert updated.status == VisitStatus.CHECKED_OUT
    assert updated.checked_out_at is not None


@pytest.mark.asyncio
async def test_cancel_transitions_to_cancelled(db_session_with_tenant):
    session, tenant_id = db_session_with_tenant
    visitor = Visitor(tenant_id=tenant_id, name="Test")
    session.add(visitor)
    await session.flush()

    visit = Visit(
        tenant_id=tenant_id,
        visitor_id=visitor.id,
        purpose="Meeting",
        status=VisitStatus.SCHEDULED,
    )
    session.add(visit)
    await session.flush()

    service = VisitService(session)
    updated = await service.cancel(visit.id)
    assert updated.status == VisitStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_already_checked_out_raises(db_session_with_tenant):
    session, tenant_id = db_session_with_tenant
    visitor = Visitor(tenant_id=tenant_id, name="Test")
    session.add(visitor)
    await session.flush()

    visit = Visit(
        tenant_id=tenant_id,
        visitor_id=visitor.id,
        purpose="Meeting",
        status=VisitStatus.CHECKED_OUT,
        checked_in_at=datetime.now(timezone.utc),
        checked_out_at=datetime.now(timezone.utc),
    )
    session.add(visit)
    await session.flush()

    service = VisitService(session)
    with pytest.raises(VisitStateError):
        await service.cancel(visit.id)
