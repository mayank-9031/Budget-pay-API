# app/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from .config import settings
import logging
import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Engine configuration with production-ready pool settings
engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,          # Check connection before using
    "pool_recycle": 1800,           # Recycle connections after 30 minutes
    "pool_size": 20,                # Main pool size for normal load
    "max_overflow": 30,             # Allow up to 30 additional temporary connections
    "pool_timeout": 30,             # Wait up to 30 seconds for connection
    "connect_args": {
        "timeout": 10,              # Connection timeout in seconds
        "command_timeout": 60,      # Command timeout in seconds
        "server_settings": {
            "application_name": "budget-pay-api",
            "tcp_keepalives_idle": "30",     # Idle time before sending keepalive
            "tcp_keepalives_interval": "10",  # Interval between keepalives
            "tcp_keepalives_count": "5"       # Number of keepalive attempts
        }
    }
}

# Add Supabase-specific configuration
if settings.is_supabase:
    # Comprehensive Supabase/PgBouncer compatibility configuration
    engine_kwargs.update({
        # Disable all forms of prepared statements
        "pool_pre_ping": True,
        "pool_reset_on_return": "commit",  # Reset connection state
        "connect_args": {
            "timeout": 10,
            "command_timeout": 60,
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": None,
            "server_settings": {
                "application_name": "budget-pay-api",
                "jit": "off",  # Disable JIT compilation
                "plan_cache_mode": "force_custom_plan"  # Force custom plans
            }
        }
    })
    logger.info("🔧 Configured engine for Supabase with comprehensive prepared statement disabling")
else:
    # Keep original server settings for non-Supabase databases
    pass

# Create the async engine with improved connection handling
engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
    # Additional Supabase-specific parameters
    execution_options={
        "compiled_cache": {},  # Disable compiled statement cache
        "autocommit": False,
    } if settings.is_supabase else {}
)

# AsyncSession factory using async_sessionmaker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Base class for all models
Base = declarative_base()

# Connection cleanup utility
async def cleanup_connections():
    """Clean up any stale connections"""
    try:
        await engine.dispose()
        logger.info("🧹 Connection pool cleaned up")
    except Exception as e:
        logger.warning(f"Connection cleanup warning: {str(e)}")

# Connection health check
async def check_db_connection():
    """Check if database connection is healthy"""
    session = None
    try:
        session = AsyncSessionLocal()
        # Use text() for raw SQL
        from sqlalchemy import text
        await session.execute(text("SELECT 1"))
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        if session:
            try:
                await session.rollback()
            except:
                pass  # Ignore rollback errors
        return False
    finally:
        if session:
            try:
                await session.close()
            except:
                pass  # Ignore close errors

# Dependency to get DB session with proper exception handling
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get database session.
    Simplified version that properly handles async generator lifecycle.
    """
    session = None
    try:
        # Create a session
        session = AsyncSessionLocal()
        
        # Test the connection with a simple query
        from sqlalchemy import text
        await session.execute(text("SELECT 1"))
        
        # Yield the session to the caller
        logger.debug("Database session created successfully")
        yield session
        
        # Commit any pending transactions
        await session.commit()
        
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        
        # Rollback on error
        if session:
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {str(rollback_error)}")
        
        # Re-raise the exception
        raise
        
    finally:
        # Always close the session
        if session:
            try:
                await session.close()
                logger.debug("Database session closed")
            except Exception as close_error:
                logger.error(f"Error closing database session: {str(close_error)}")

# Alternative session dependency with retry logic (use this if needed)
async def get_async_session_with_retry() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency with retry logic.
    Use this for critical operations that need retry capability.
    """
    max_retries = 3
    retry_delay = 1
    session = None
    
    for attempt in range(max_retries):
        try:
            session = AsyncSessionLocal()
            
            # Test connection
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            
            logger.debug(f"Database session created (attempt {attempt + 1})")
            yield session
            
            # Commit on success
            await session.commit()
            return  # Success, exit retry loop
            
        except Exception as e:
            logger.error(f"Database session error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            
            # Cleanup current session
            if session:
                try:
                    await session.rollback()
                    await session.close()
                except:
                    pass
                session = None
            
            # If this was the last attempt, raise the exception
            if attempt == max_retries - 1:
                logger.error("All database connection attempts failed")
                raise
            
            # Wait before retrying
            import asyncio
            await asyncio.sleep(retry_delay * (attempt + 1))
        
        finally:
            # Final cleanup
            if session:
                try:
                    await session.close()
                except:
                    pass

# Context manager for manual session handling
@asynccontextmanager
async def get_db_session():
    """Context manager for database sessions with automatic cleanup"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database transaction error: {str(e)}")
        raise
    finally:
        await session.close()

# Connection pool status
async def get_pool_status():
    """Get connection pool status for monitoring"""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checkedin": pool.checkedin(),
        "checkedout": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow()
    }

# Graceful shutdown
async def close_db_connection():
    """Close all database connections gracefully"""
    try:
        await engine.dispose()
        logger.info("Database connections closed gracefully")
    except Exception as e:
        logger.error(f"Error closing database connections: {str(e)}")

# Startup event - test connection
async def init_db():
    """Initialize database connection and test it with retry logic"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Testing database connection... (attempt {attempt + 1}/{max_retries})")
            
            # Add a small delay before each attempt (except the first)
            if attempt > 0:
                import asyncio
                await asyncio.sleep(retry_delay * attempt)
            
            if await check_db_connection():
                logger.info("✅ Database connection successful")
                try:
                    pool_status = await get_pool_status()
                    logger.info(f"📊 Connection pool status: {pool_status}")
                except Exception as pool_error:
                    # Log pool status error but don't fail initialization
                    logger.warning(f"Unable to get pool status: {str(pool_error)}")
                return  # Success, exit function
            else:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection failed on attempt {attempt + 1}, retrying...")
                    continue
                else:
                    logger.error("❌ Database connection failed after all retries")
                    raise Exception("Database connection check failed after all retries")
                    
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database initialization error on attempt {attempt + 1}: {str(e)}, retrying...")
                continue
            else:
                logger.error(f"Database initialization error after all retries: {str(e)}")
                raise