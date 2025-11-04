"""
Database configuration and session management for Neon PostgreSQL.
"""

from typing import AsyncGenerator

from sqlalchemy import create_engine, event, pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from backend.src.core.config import settings

# Base class for ORM models
Base = declarative_base()

# Synchronous engine for migrations
sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"),
    poolclass=pool.QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

# Asynchronous engine for API operations
async_engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

# Session makers
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
    class_=Session,
)

AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Database session dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Connection event handlers for optimal PostgreSQL performance
@event.listens_for(sync_engine, "connect")
def set_postgresql_pragmas(dbapi_conn, connection_record):
    """Set PostgreSQL connection pragmas for optimal performance."""
    cursor = dbapi_conn.cursor()

    # Set statement timeout (30 seconds)
    cursor.execute("SET statement_timeout = 30000")

    # Set work memory for complex queries
    cursor.execute("SET work_mem = '16MB'")

    cursor.close()


async def init_db() -> None:
    """
    Initialize database tables.

    Note: In production, use Alembic migrations instead.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()
