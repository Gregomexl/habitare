"""
FastAPI Dependency Injection
Database session and authentication dependencies
"""
from typing import Annotated, AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency with automatic cleanup.

    Uses yield pattern for automatic session closing after request completion.
    This is the FastAPI best practice for managing database sessions.
    """
    async with async_session() as session:
        yield session


# Type alias for cleaner endpoint signatures
AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]
