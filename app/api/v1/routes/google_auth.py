# app/api/v1/routes/google_auth.py
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status, Security
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_user_manager, UserManager, create_access_token
from app.core.database import get_async_session
from app.core.google_auth import create_oauth_flow, exchange_code_for_token
from app.schemas.user import GoogleAuthRequest, GoogleAuthResponse
from app.core.config import settings

router = APIRouter()

# Define security scheme
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

@router.post("/login", response_model=GoogleAuthResponse)
async def google_login(
    request: GoogleAuthRequest,
    request_obj: Request
):
    """
    Initiate Google OAuth login flow
    """
    try:
        # Create OAuth flow
        flow = create_oauth_flow(request.redirect_uri)
        
        # Generate authorization URL with state
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        
        # Store state in session for verification during callback
        request_obj.session["oauth_state"] = state
        
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate Google login: {str(e)}"
        )

@router.get("/callback")
async def google_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager)
):
    """
    Handle Google OAuth callback
    """
    # Check for error
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {error}"
        )
    
    try:
        # Exchange code for token
        access_token, user_info = await exchange_code_for_token(code)
        
        # Get user email from Google profile
        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        # If user doesn't exist, create a new one
        if not user:
            # Create user with Google info
            new_user = User(
                email=email,
                hashed_password="",  # No password for Google users
                is_active=True,
                is_verified=True,  # Google already verified the email
                full_name=user_info.get("name"),
                google_id=user_info.get("sub"),
                google_access_token=access_token,
                google_token_expiry=datetime.utcnow() + timedelta(hours=1)
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            user = new_user
        else:
            # Update existing user with Google info
            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    google_id=user_info.get("sub"),
                    google_access_token=access_token,
                    google_token_expiry=datetime.utcnow() + timedelta(hours=1),
                    full_name=user_info.get("name") if user_info.get("name") else user.full_name
                )
            )
            await db.commit()
            await db.refresh(user)
        
        # Generate JWT token
        token = create_access_token(str(user.id))
        
        # Construct redirect URL with token
        redirect_url = f"{settings.FRONTEND_URL}/auth/google-callback?access_token={token}&token_type=bearer&user_id={user.id}&email={email}"
        
        # Set token in cookies as a backup method
        response = RedirectResponse(url=redirect_url)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax"
        )
        
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process Google callback: {str(e)}"
        )

@router.get("/verify-token", summary="Verify authentication token", description="Requires a valid JWT token in the Authorization header")
async def verify_token(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    credentials: HTTPAuthorizationCredentials = Security(optional_security)
) -> Dict[str, Any]:
    """
    Verify that the token is valid and return user information.
    This endpoint can be used by the frontend to check if the user is authenticated.
    **Important**: You must include a valid JWT token in the Authorization header.
    Format: `Authorization: Bearer YOUR_TOKEN_HERE`
    """
    import jwt
    from datetime import datetime
    
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
        
        # Decode the token with audience validation
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM],
            audience=["fastapi-users:auth"]  # Match the audience set by FastAPI Users
        )
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > payload.get("exp", 0):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Return user info
        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
        }
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