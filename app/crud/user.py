# app/crud/user.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.auth import User
from typing import Optional, List
import uuid

async def get_user_by_email(email: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def get_user_by_id(user_id: uuid.UUID, db: AsyncSession) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

# If you need to update custom fields manually:
async def update_user_fields(user: User, full_name: str, monthly_income: float, db: AsyncSession) -> User:
    user.full_name = full_name
    user.monthly_income = monthly_income
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
