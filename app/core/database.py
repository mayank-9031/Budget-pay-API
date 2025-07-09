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

# Create the async engine with improved connection handling
engine = create_async_engine(
    settings.DATABASE_URL,  # Direct use since we have the right format
    echo=False,
    future=True,
    pool_pre_ping=True,    # Check connection before using
    pool_recycle=300,      # Recycle connections after 5 minutes
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