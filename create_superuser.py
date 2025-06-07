#!/usr/bin/env python3
"""
Standalone script to create a superuser for the Budget Pay API
Usage: python create_superuser.py
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.auth import User, UserManager, UserCreate
from fastapi_users.db import SQLAlchemyUserDatabase

async def create_superuser():
    print("Creating superuser...")
    
    # Get user input
    email = input("Enter superuser email: ") or "admin@example.com"
    password = input("Enter superuser password: ") or "admin123"
    full_name = input("Enter full name (optional): ") or "System Administrator"
    
    # Create engine and session maker
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Create async session
    async with async_session_maker() as session:
        try:
            # Get user database and manager
            user_db = SQLAlchemyUserDatabase(session, User)
            user_manager = UserManager(user_db)
            
            # Check if user already exists
            existing_user = await user_manager.get_by_email(email)
            if existing_user:
                print(f"User with email {email} already exists!")
                return
            
            # Create superuser
            user_create = UserCreate(
                email=email,
                password=password,
                full_name=full_name,
                is_superuser=True,
                is_verified=True
            )
            
            superuser = await user_manager.create(user_create)
            print(f"✅ Superuser created successfully!")
            print(f"📧 Email: {superuser.email}")
            print(f"👤 Name: {superuser.full_name}")
            print(f"🔑 ID: {superuser.id}")
            
        except Exception as e:
            print(f"❌ Error creating superuser: {e}")
        finally:
            await session.close()
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_superuser())