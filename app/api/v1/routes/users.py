# app/api/v1/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import current_active_user, User, UserRead
from app.core.database import get_async_session
from typing import List

router = APIRouter(prefix="/users", tags=["User Management"])

# ------------------------------------------------------------
# CUSTOM USER ENDPOINTS (Business Logic)
# ------------------------------------------------------------

# Note: Basic user management routes (/users/me, PATCH /users/me, etc.) 
# are already handled by FastAPI-Users in main.py
# These are additional custom endpoints for your business logic

@router.get("/list", response_model=List[UserRead])
async def list_all_users(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """
    List all users (Admin only)
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not enough permissions. Admin access required."
        )
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    return users

@router.get("/profile/extended")
async def get_extended_profile(
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get extended user profile with additional statistics
    """
    # Add your custom logic here (e.g., expense summaries, goal progress, etc.)
    return {
        "user_info": {
            "id": current_user.id,
            "email": current_user.email,
            "monthly_income": current_user.monthly_income,
            "is_active": current_user.is_active,
            "is_verified": current_user.is_verified,
            "created_at": current_user.created_at
        },
        "statistics": {
            "total_expenses": 0,  # Calculate from database
            "total_goals": 0,     # Calculate from database
            "budget_utilization": 0  # Calculate percentage
        }
    }

@router.post("/deactivate")
async def deactivate_account(
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Deactivate current user account
    """
    current_user.is_active = False
    await db.commit()
    return {"message": "Account deactivated successfully"}