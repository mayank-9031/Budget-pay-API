# app/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from .config import settings
import logging
import asyncio
from typing import AsyncGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Engine configuration - start with your existing settings
engine_kwargs = {
    "echo": False,
    "future": True,
    # Keep the pool small but responsive on Render starter instances
    "pool_size": 5,
    "max_overflow": 5,
    "pool_timeout": 30,       # Seconds to wait for a free connection
    "pool_pre_ping": True,    # Check connection before using
    "pool_recycle": 300,      # Recycle connections after 5 minutes
}

# Add Supabase-specific configuration to fix prepared statement issues
if settings.is_supabase:
    # Disable prepared statements for Supabase/PgBouncer compatibility
    # Also set an explicit connect timeout to fail fast instead of hanging.
    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "timeout": 10,  # seconds for asyncpg connect
    }
    # Preserve any pre-existing connect_args
    existing = engine_kwargs.get("connect_args", {})
    existing.update(connect_args)
    engine_kwargs["connect_args"] = existing
    logger.info("🔧 Configured engine for Supabase/PgBouncer (prepared statements disabled, connect timeout set)")

# Create the async engine with improved connection handling
engine = create_async_engine(
    settings.DATABASE_URL,  # Direct use since we have the right format
    **engine_kwargs
)

# AsyncSession factory using async_sessionmaker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Base class for all models
Base = declarative_base()

# Dependency to get DB session with proper exception handling
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    # Create a session
    session = AsyncSessionLocal()
    try:
        # Yield the session to the caller
        yield session
    except Exception as e:
        # Log the error and rollback
        logger.error(f"Database session error: {str(e)}")
        await session.rollback()
        raise
    finally:
        # Always close the session
        await session.close()
        logger.debug("Database session closed")