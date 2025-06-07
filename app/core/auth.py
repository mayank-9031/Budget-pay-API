# app/core/auth.py

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users import schemas

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, get_async_session
from .config import settings

# 1. Define User DB model
class User(Base):
    __tablename__ = "users"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Additional fields
    full_name = Column(String, nullable=True)
    monthly_income = Column(String, nullable=True)
    savings_goal_amount = Column(String, nullable=True)
    savings_goal_deadline = Column(DateTime, nullable=True)

    # Add relationships for categories, expenses, transactions, goals
    categories = relationship(
        "Category",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    expenses = relationship(
        "Expense", 
        back_populates="user",
        cascade="all, delete-orphan",
    )
    transactions = relationship(
        "Transaction",
        back_populates="user", 
        cascade="all, delete-orphan",
    )
    goals = relationship(
        "Goal",
        back_populates="user",
        cascade="all, delete-orphan",
    )

# 2. Pydantic schemas
class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: Optional[str] = None
    monthly_income: Optional[str] = None
    savings_goal_amount: Optional[str] = None
    savings_goal_deadline: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class UserCreate(schemas.BaseUserCreate):
    full_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserUpdate(schemas.BaseUserUpdate):
    full_name: Optional[str] = None
    monthly_income: Optional[str] = None
    savings_goal_amount: Optional[str] = None
    savings_goal_deadline: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# 3. User Manager
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[any] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[any] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[any] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")

# 4. User Database
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)

# 5. User Manager dependency
async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

# 6. Authentication - FIXED: Correct tokenUrl to match your API structure
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.SECRET_KEY, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# 7. FastAPI Users instance
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# 8. Current user dependency
current_active_user = fastapi_users.current_user(active=True)

# Export for other modules
__all__ = [
    "fastapi_users",
    "auth_backend", 
    "current_active_user",
    "get_user_db",
    "User",
    "UserRead",
    "UserCreate", 
    "UserUpdate",
]