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


# Default categories to be created for every new user
DEFAULT_CATEGORIES: List[dict] = [
    {"name": "Food", "default_percentage": 20.0, "is_fixed": False, "is_default": True},
    {"name": "Travel", "default_percentage": 20.0, "is_fixed": False, "is_default": True},
    {"name": "Shopping", "default_percentage": 20.0, "is_fixed": False, "is_default": True},
    {"name": "Miscellaneous", "default_percentage": 10.0, "is_fixed": False, "is_default": True},
    {"name": "Housing", "default_percentage": 30.0, "is_fixed": True, "is_default": True},
]

async def seed_default_categories_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Category]:
    """Ensure the user has the default categories; create missing ones.

    Returns the list of categories that were created (empty if none were needed).
    """
    # Fetch existing category names for the user (case-insensitive set)
    result = await db.execute(select(Category.name).where(Category.user_id == user_id))
    existing_rows = result.all()
    existing_names_lower = {row[0].lower() for row in existing_rows}

    categories_to_create: List[Category] = []
    for cat in DEFAULT_CATEGORIES:
        if cat["name"].lower() not in existing_names_lower:
            categories_to_create.append(
                Category(
                    user_id=user_id,
                    name=cat["name"],
                    description=None,
                    default_percentage=float(cat["default_percentage"]),
                    is_fixed=bool(cat["is_fixed"]),
                    is_default=bool(cat.get("is_default", True)),
                )
            )

    if categories_to_create:
        db.add_all(categories_to_create)
        await db.commit()
        for c in categories_to_create:
            await db.refresh(c)

    return categories_to_create