"""
Pytest configuration and shared fixtures
"""
import uuid
from contextlib import asynccontextmanager
import pytest_asyncio
from sqlalchemy import text, insert
from app.core.database import async_session, engine
from app.models import User, UserRole


@pytest_asyncio.fixture(scope="function")
async def manage_engine():
    """
    Function-scoped fixture to manage engine lifecycle.
    Used by database fixtures to ensure clean connections between tests.
    """
    yield
    await engine.dispose()


@asynccontextmanager
async def tenant_context(tenant_id: uuid.UUID):
    """
    Context manager for setting tenant context in RLS-enabled database.

    Usage:
        async with tenant_context(tenant_id):
            # Database queries here will be scoped to tenant_id
    """
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'")
            )
            yield session


@pytest_asyncio.fixture(scope="function")
async def test_users(manage_engine):
    """
    Create test users for two different tenants.
    Cleans up after test completion.

    Depends on manage_engine to ensure clean engine state.
    """
    tenant1_id = uuid.uuid4()
    tenant2_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    # Setup: Create user for tenant 1 with proper tenant context
    async with tenant_context(tenant1_id) as session:
        await session.execute(
            insert(User).values(
                id=user1_id,
                tenant_id=tenant1_id,
                email="user1@tenant1.com",
                password_hash="hash1",
                role=UserRole.TENANT_USER,
                full_name="User One"
            )
        )

    # Create user for tenant 2 with proper tenant context
    async with tenant_context(tenant2_id) as session:
        await session.execute(
            insert(User).values(
                id=user2_id,
                tenant_id=tenant2_id,
                email="user2@tenant2.com",
                password_hash="hash2",
                role=UserRole.TENANT_USER,
                full_name="User Two"
            )
        )

    # Return test data
    yield tenant1_id, tenant2_id, user1_id, user2_id

    # Cleanup: Delete test data for each tenant with proper tenant context
    async with tenant_context(tenant1_id) as session:
        await session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": str(user1_id)}
        )

    async with tenant_context(tenant2_id) as session:
        await session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": str(user2_id)}
        )
