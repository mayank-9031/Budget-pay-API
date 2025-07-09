"""
Database utilities for connection management and error handling
"""
import asyncio
import functools
import logging
from typing import Callable, Any, TypeVar, cast, Awaitable

logger = logging.getLogger(__name__)

# Define a type variable for the return type of the decorated function
T = TypeVar('T')

def with_db_retry(
    max_retries: int = 3,
    retry_delay: float = 0.5
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator that retries database operations on connection errors.
    
    Args:
        max_retries: Maximum number of retries before giving up
        retry_delay: Delay between retries in seconds
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            retries = 0
            last_error = None
            
            while retries <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Check if it's a connection error
                    error_name = type(e).__name__
                    if any(err in error_name for err in [
                        "ConnectionError", "OperationalError", 
                        "ConnectionDoesNotExistError", "ConnectionRefusedError"
                    ]):
                        retries += 1
                        last_error = e
                        
                        if retries <= max_retries:
                            delay = retry_delay * (2 ** (retries - 1))  # Exponential backoff
                            logger.warning(
                                f"Database connection error: {str(e)}. "
                                f"Retrying in {delay:.2f}s... (Attempt {retries}/{max_retries})"
                            )
                            await asyncio.sleep(delay)
                        continue
                    else:
                        # Not a connection error, re-raise immediately
                        raise
            
            # If we get here, we've exhausted all retries
            logger.error(f"Database operation failed after {max_retries} retries: {last_error}")
            if last_error:
                raise last_error
            else:
                raise RuntimeError("Database operation failed with unknown error")
            
        return cast(Callable[..., Awaitable[T]], wrapper)
    
    return decorator 