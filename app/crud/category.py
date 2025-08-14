# app/crud/category.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.models.category import Category
from typing import List, Optional
import uuid
from app.schemas.category import CategoryCreate, CategoryUpdate

async def get_categories_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Category]:
    result = await db.execute(select(Category).where(Category.user_id == user_id))
    return result.scalars().all()

async def get_category_by_id(category_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Optional[Category]:
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_category_for_user(user_id: uuid.UUID, cat_in: CategoryCreate, db: AsyncSession) -> Category:
    new_cat = Category(**cat_in.dict(), user_id=user_id)
    db.add(new_cat)
    await db.commit()
    await db.refresh(new_cat)
    return new_cat

async def update_category(category: Category, cat_in: CategoryUpdate, db: AsyncSession) -> Category:
    for field, value in cat_in.dict(exclude_unset=True).items():
        setattr(category, field, value)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

async def delete_category(category: Category, db: AsyncSession) -> None:
    await db.delete(category)
    await db.commit()


async def get_category_by_name_for_user(name: str, user_id: uuid.UUID, db: AsyncSession) -> Optional[Category]:
    """Case-insensitive lookup of a category by name for a given user."""
    result = await db.execute(
        select(Category).where(
            Category.user_id == user_id,
            func.lower(Category.name) == func.lower(name),
        )
    )
    return result.scalar_one_or_none()