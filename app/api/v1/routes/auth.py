# app/api/v1/routes/auth.py
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_async_session
from app.core.auth import User
from app.api.deps import get_optional_current_user

router = APIRouter(tags=["Authentication"])

# Match the exact path that the frontend is calling
@router.post("/jwt/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response
):
    """
    Logout endpoint that doesn't require authentication.
    This endpoint will clear the access token cookie if present.
    """
    # Clear the cookie if it exists
    response.delete_cookie(key="access_token")
    
    return {"detail": "Successfully logged out"} 