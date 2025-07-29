# app/api/v1/routes/categories.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.schemas.category import CategoryCreate, Category, CategoryUpdate
from app.crud.category import (
    create_category_for_user,
    get_categories_for_user,
    get_category_by_id,
    update_category,
    delete_category,
)
from app.core.database import get_async_session
from app.core.auth import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("", response_model=List[Category])
async def read_categories(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    categories = await get_categories_for_user(user_id, db)
    return categories

@router.post("", response_model=Category, status_code=status.HTTP_201_CREATED)
async def create_category(
    cat_in: CategoryCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    return await create_category_for_user(user_id, cat_in, db)

@router.get("/{category_id}", response_model=Category)
async def read_category(
    category_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    category = await get_category_by_id(category_id, user_id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category

@router.patch("/{category_id}", response_model=Category)
async def update_category_endpoint(
    category_id: uuid.UUID,
    cat_in: CategoryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    category = await get_category_by_id(category_id, user_id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    return await update_category(category, cat_in, db)

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    category = await get_category_by_id(category_id, user_id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    await delete_category(category, db)
    return None
