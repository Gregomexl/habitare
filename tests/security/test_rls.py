"""
Row-Level Security (RLS) Tests
Verification script for Subphase 1.5

Tests that RLS policies properly enforce tenant isolation at the database level.
"""
import uuid
import pytest
from sqlalchemy import select, insert, update
from sqlalchemy.exc import DBAPIError

from app.core.database import async_session
from app.models import User, UserRole
from tests.conftest import tenant_context


@pytest.mark.asyncio
async def test_cross_tenant_read_blocked(test_users):
    """Test that RLS blocks cross-tenant read access."""
    tenant1_id, tenant2_id, user1_id, user2_id = test_users

    async with tenant_context(tenant1_id) as session:
        # Query all users - should only see tenant 1's users
        result = await session.execute(select(User))
        users = result.scalars().all()

        assert len(users) == 1, f"Expected 1 user, got {len(users)}"
        assert users[0].id == user1_id, "Should only see tenant 1's user"
        assert users[0].tenant_id == tenant1_id

        # Try to query tenant 2's user by ID - should return empty
        result = await session.execute(
            select(User).where(User.id == user2_id)
        )
        user = result.scalar_one_or_none()

        assert user is None, "Should not be able to see tenant 2's user"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_type", ["insert", "update"])
async def test_cross_tenant_write_blocked(test_users, operation_type):
    """Test that RLS blocks cross-tenant write access (INSERT/UPDATE)."""
    tenant1_id, tenant2_id, user1_id, user2_id = test_users

    if operation_type == "insert":
        # Test INSERT with wrong tenant_id
        async with tenant_context(tenant1_id) as session:
            new_user_id = uuid.uuid4()
            with pytest.raises(DBAPIError, match="row-level security policy"):
                await session.execute(
                    insert(User).values(
                        id=new_user_id,
                        tenant_id=tenant2_id,  # Wrong tenant!
                        email="hacker@tenant2.com",
                        password_hash="hash",
                        role=UserRole.TENANT_USER
                    )
                )
                await session.flush()  # Force the check

    elif operation_type == "update":
        # Test UPDATE to change tenant_id
        async with tenant_context(tenant1_id) as session:
            # Get tenant 1's user
            result = await session.execute(select(User))
            user = result.scalar_one()

            # Try to update tenant_id to tenant 2 - should fail
            with pytest.raises(DBAPIError, match="row-level security policy"):
                await session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(tenant_id=tenant2_id)
                )
                await session.flush()  # Force the check


@pytest.mark.asyncio
async def test_without_tenant_context(test_users):
    """Test that queries without tenant context return no results."""
    tenant1_id, tenant2_id, user1_id, user2_id = test_users

    async with async_session() as session:
        # Don't set tenant context - should see nothing
        result = await session.execute(select(User))
        users = result.scalars().all()

        # Without tenant context set, RLS policy will try to read
        # current_setting which returns NULL, so nothing matches
        assert len(users) == 0, "Without tenant context, should see no users"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "update"])
async def test_correct_tenant_context_allows_access(test_users, operation):
    """Test that correct tenant context allows normal operations."""
    tenant1_id, tenant2_id, user1_id, user2_id = test_users

    if operation == "read":
        async with tenant_context(tenant1_id) as session:
            # Should be able to read own data
            result = await session.execute(select(User).where(User.id == user1_id))
            user = result.scalar_one()
            assert user.id == user1_id

    elif operation == "update":
        # Test update operation
        async with tenant_context(tenant1_id) as session:
            await session.execute(
                update(User)
                .where(User.id == user1_id)
                .values(full_name="Updated Name")
            )

        # Verify update in new transaction
        async with tenant_context(tenant1_id) as session:
            result = await session.execute(select(User).where(User.id == user1_id))
            user = result.scalar_one()
            assert user.full_name == "Updated Name"
