"""
Test database connection
Simple verification script for Subphase 1.2
"""
import asyncio
from sqlalchemy import text
from app.core.database import async_session


async def test_db_connection():
    """Test database connection with a simple SELECT 1 query."""
    print("Testing database connection...")

    async with async_session() as session:
        result = await session.execute(text("SELECT 1 as test"))
        row = result.first()

        if row and row.test == 1:
            print("[PASS] Database connection successful!")
            print(f"       Query result: {row.test}")
            return True
        else:
            print("[FAIL] Database connection failed!")
            return False


async def test_db_info():
    """Get PostgreSQL version information."""
    print("\nGetting database information...")

    async with async_session() as session:
        result = await session.execute(text("SELECT version()"))
        version = result.scalar()
        print(f"[INFO] PostgreSQL Version:\n       {version}")

        result = await session.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        print(f"[INFO] Current Database: {db_name}")


async def main():
    """Run all tests."""
    await test_db_connection()
    await test_db_info()


if __name__ == "__main__":
    asyncio.run(main())
