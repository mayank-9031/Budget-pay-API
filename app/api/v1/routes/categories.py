# app/api/v1/routes/categories.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.crud.category import (
    create_category_for_user,
    get_categories_for_user,
    get_category_by_id,
    update_category,
    delete_category,
)
from app.core.database import get_async_session
from app.core.auth import current_active_user, User

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("", response_model=List[CategoryRead])
async def read_categories(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    categories = await get_categories_for_user(user.id, db)
    return categories

@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    cat_in: CategoryCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await create_category_for_user(user.id, cat_in, db)

@router.get("/{category_id}", response_model=CategoryRead)
async def read_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    category = await get_category_by_id(category_id, user.id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category

@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category_endpoint(
    category_id: uuid.UUID,
    cat_in: CategoryUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    category = await get_category_by_id(category_id, user.id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    return await update_category(category, cat_in, db)

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    category = await get_category_by_id(category_id, user.id, db)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    await delete_category(category, db)
    return None
