"""
Database Configuration and Session Management
Using SQLAlchemy 2.0 async patterns with FastAPI best practices
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Create async engine
# Production-ready configuration with disconnect handling and connection recycling
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # Test connections before checkout (pessimistic disconnect handling)
    pool_recycle=3600,   # Recycle connections after 1 hour to prevent stale connections
    future=True
)

# Create async session factory
# Critical: expire_on_commit=False prevents detached instance errors in async contexts
async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False
)
