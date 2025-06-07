# app/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Create the async engine - Use the new method from config
engine = create_async_engine(
    settings.get_database_url,  # Changed from settings.DATABASE_URL
    echo=False,                # set to True for SQL echo
    future=True,
)

# AsyncSession factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Base class for all models
Base = declarative_base()

# Dependency to get DB session
async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()