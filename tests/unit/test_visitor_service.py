import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text
from app.core.database import async_session
from app.models.visitor import Visitor
from app.services.visitor_service import VisitorService


@pytest_asyncio.fixture
async def db_with_tenant(manage_engine):
    """Yields (session, tenant_id) with RLS context set."""
    tenant_id = uuid.uuid4()
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'")
            )
            yield session, tenant_id
            # rollback cleans up — no explicit delete needed


@pytest.mark.asyncio
async def test_create_visitor(db_with_tenant):
    session, tenant_id = db_with_tenant
    service = VisitorService(session)
    visitor = await service.create_or_get(
        tenant_id=tenant_id,
        name="Jane Smith",
        email="jane@example.com",
        phone=None,
    )
    assert visitor.id is not None
    assert visitor.name == "Jane Smith"
    assert visitor.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_email_deduplication(db_with_tenant):
    """Same email within same tenant returns existing visitor."""
    session, tenant_id = db_with_tenant
    service = VisitorService(session)
    v1 = await service.create_or_get(tenant_id=tenant_id, name="Jane", email="jane@example.com")
    v2 = await service.create_or_get(tenant_id=tenant_id, name="Jane Duplicate", email="jane@example.com")
    assert v1.id == v2.id


@pytest.mark.asyncio
async def test_no_email_always_creates(db_with_tenant):
    """Walk-ins with no email always create a new record."""
    session, tenant_id = db_with_tenant
    service = VisitorService(session)
    v1 = await service.create_or_get(tenant_id=tenant_id, name="Walk-in A", email=None)
    v2 = await service.create_or_get(tenant_id=tenant_id, name="Walk-in B", email=None)
    assert v1.id != v2.id
