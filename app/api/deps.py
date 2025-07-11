# app/api/deps.py
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.core.database import get_async_session
from app.core.auth import current_active_user
from app.core.auth import User

# Example:
async def get_db_session() -> AsyncSession:
    return Depends(get_async_session)

async def get_current_user(user: User = Depends(current_active_user)) -> User:
    return user
