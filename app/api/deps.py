# app/api/deps.py
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt
import uuid

from app.core.database import get_async_session
from app.core.auth import current_active_user
from app.core.auth import User
from app.core.config import settings

# Security schemes
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# Example:
async def get_db_session() -> AsyncSession:
    return Depends(get_async_session)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
) -> User:
    """
    Enhanced dependency to get the current user from token in various locations:
    - Authorization header
    - Query parameters
    - Cookies
    """
    # Try to get token from various sources
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    # From Authorization header
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
    elif credentials and credentials.credentials:
        token = credentials.credentials
    
    # From query parameter
    if not token:
        token = request.query_params.get("token") or request.query_params.get("access_token")
    
    # From cookie
    if not token:
        token = request.cookies.get("access_token")
        # Remove "Bearer " prefix if present in cookie
        if token and token.startswith("Bearer "):
            token = token[7:]
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Convert SecretStr to str if needed
        secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
        
        # Decode the token
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )
        
        # Get user ID from token
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Convert user_id to UUID
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID format in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database directly
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active by comparing the value, not the Column object itself
        is_active = getattr(user, "is_active", False)
        if is_active is False:  # Compare with boolean value, not the Column
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Optional version of get_current_user that doesn't raise exceptions
async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
) -> Optional[User]:
    """
    Similar to get_current_user but returns None instead of raising an exception
    when authentication fails. Useful for endpoints like logout that should work
    even if the user is not authenticated.
    """
    try:
        return await get_current_user(request, db, credentials)
    except HTTPException:
        return None
