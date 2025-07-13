# app/api/v1/routes/users.py
import uuid
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi_users import BaseUserManager
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import current_active_user, get_user_manager, User
from app.core.database import get_async_session
from app.core.auth import UserRead, UserUpdate  # your Pydantic schemas
from app.api.deps import get_current_user  # Import our enhanced dependency

router = APIRouter(tags=["User Management"])

# 1) GET /users/me
@router.get("/me", response_model=UserRead)
async def read_own_profile(
    request: Request,
    user: User = Depends(get_current_user)  # Use our enhanced dependency
):
    """Get current user's profile"""
    return user

# 2) PATCH /users/me
@router.patch("/me", response_model=UserRead)
async def update_own_profile(
    user_update: UserUpdate,
    request: Request,
    user: User = Depends(get_current_user),  # Use our enhanced dependency
    user_manager: BaseUserManager[User, uuid.UUID] = Depends(get_user_manager),
    db: AsyncSession = Depends(get_async_session),
):
    """Update current user's profile"""
    try:
        # Create update dictionary, excluding None values
        update_dict = user_update.dict(exclude_unset=True)
        
        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )
        
        # Convert user.id to UUID
        user_id = uuid.UUID(str(user.id))
        
        # Update user directly in database
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**update_dict)
        )
        
        # Commit the transaction
        await db.commit()
        
        # Fetch the updated user
        result = await db.execute(select(User).where(User.id == user_id))
        updated_user = result.scalars().first()
        
        return updated_user
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred while updating profile: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

# 3) DELETE /users/me
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_profile(
    request: Request,
    user: User = Depends(get_current_user),
    user_manager: BaseUserManager[User, uuid.UUID] = Depends(get_user_manager),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete current user's account permanently"""
    try:
        # Use user_manager for deletion (handles cleanup)
        await user_manager.delete(user)
        
        # Commit the transaction
        await db.commit()
        
        return  # 204 No Content
        
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deleting account"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

# 4) List users with pagination and security
@router.get("/list-all", response_model=List[UserRead])
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    List users with pagination
    Note: Consider adding admin-only access in production
    """
    try:
        # Add pagination to prevent large data dumps
        if limit > 100:
            limit = 100
            
        query = select(User).offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()
        
        return users
        
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while fetching users"
        )

@router.get("/profile/extended")
async def get_extended_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get extended user profile with additional statistics
    """
    try:
        return {
            "user_info": {
                "id": str(current_user.id),
                "email": current_user.email,
                "monthly_income": current_user.monthly_income,
                "is_active": current_user.is_active,
                "is_verified": current_user.is_verified,
                "created_at": current_user.created_at.isoformat() if hasattr(current_user, "created_at") and current_user.created_at else None
            },
            "statistics": {
                "total_expenses": 0,  # Replace with actual calculation
                "total_goals": 0,     # Replace with actual calculation
                "budget_utilization": 0.0  # Replace with actual calculation
            }
        }
        
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while fetching profile"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@router.post("/deactivate")
async def deactivate_account(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Deactivate current user account (soft delete)
    """
    try:
        # Convert user.id to UUID
        user_id = uuid.UUID(str(user.id))
        
        # Check if user is already inactive
        result = await db.execute(select(User).where(User.id == user_id))
        user_db = result.scalars().first()
        
        if user_db is not None and getattr(user_db, "is_active", True) is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already deactivated"
            )
        
        # Update user directly in database
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False)
        )
        
        # Commit the transaction
        await db.commit()
        
        return {
            "message": "Account deactivated successfully",
            "user_id": str(user_id)
        }
        
    except HTTPException:
        await db.rollback()
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deactivating account"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@router.post("/reactivate")
async def reactivate_account(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Reactivate current user account
    """
    try:
        # Convert user.id to UUID
        user_id = uuid.UUID(str(user.id))
        
        # Check if user is already active
        result = await db.execute(select(User).where(User.id == user_id))
        user_db = result.scalars().first()
        
        if user_db is not None and getattr(user_db, "is_active", False) is True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already active"
            )
        
        # Update user directly in database
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=True)
        )
        
        # Commit the transaction
        await db.commit()
        
        return {
            "message": "Account reactivated successfully",
            "user_id": str(user_id)
        }
        
    except HTTPException:
        await db.rollback()
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while reactivating account"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )