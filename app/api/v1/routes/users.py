# app/api/v1/routes/users.py
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import BaseUserManager
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import current_active_user, get_user_manager, User
from app.core.database import get_async_session
from app.core.auth import UserRead, UserUpdate  # your Pydantic schemas

router = APIRouter(prefix="/users", tags=["User Management"])

# 1) GET /users/me
@router.get("/me", response_model=UserRead)
async def read_own_profile(user: User = Depends(current_active_user)):
    """Get current user's profile"""
    return user

# 2) PATCH /users/me
@router.patch("/me", response_model=UserRead)
async def update_own_profile(
    user_update: UserUpdate,
    user: User = Depends(current_active_user),
    user_manager: BaseUserManager[User, uuid.UUID] = Depends(get_user_manager),
    db: AsyncSession = Depends(get_async_session),
):
    """Update current user's profile"""
    try:
        # Create update dictionary, excluding None values
        update_dict = user_update.create_update_dict()
        
        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )
        
        # Use user_manager for updates (handles validation and hashing)
        updated_user = await user_manager.update(user, update_dict)
        
        # Commit the transaction
        await db.commit()
        
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
            detail="Database error occurred while updating profile"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

# 3) DELETE /users/me
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_profile(
    user: User = Depends(current_active_user),
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
@router.get("/list", response_model=List[UserRead])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
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
    current_user: User = Depends(current_active_user),
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
                "created_at": current_user.created_at.isoformat() if current_user.created_at else None
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
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Deactivate current user account (soft delete)
    """
    try:
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already deactivated"
            )
        
        # Deactivate the user
        current_user.is_active = False
        db.add(current_user)  # Mark for update
        await db.commit()
        
        return {
            "message": "Account deactivated successfully",
            "user_id": str(current_user.id)
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
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Reactivate current user account
    """
    try:
        if current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already active"
            )
        
        # Reactivate the user
        current_user.is_active = True
        db.add(current_user)  # Mark for update
        await db.commit()
        
        return {
            "message": "Account reactivated successfully",
            "user_id": str(current_user.id)
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