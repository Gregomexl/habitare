"""
Test database connection
Simple verification script for Subphase 1.2
"""
import pytest
from sqlalchemy import text
from app.core.database import async_session


@pytest.mark.asyncio
async def test_db_connection(manage_engine):
    """Test database connection with a simple SELECT 1 query."""
    async with async_session() as session:
        result = await session.execute(text("SELECT 1 as test"))
        row = result.first()

        assert row is not None
        assert row.test == 1


@pytest.mark.asyncio
async def test_db_info(manage_engine):
    """Get PostgreSQL version information."""
    async with async_session() as session:
        result = await session.execute(text("SELECT version()"))
        version = result.scalar()
        assert version is not None
        assert "PostgreSQL" in version

        result = await session.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        assert db_name is not None
