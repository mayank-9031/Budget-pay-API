# app/core/auth.py

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Request
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

import sendgrid
from sendgrid.helpers.mail import Mail

import asyncio
from concurrent.futures import ThreadPoolExecutor
import jwt

from .database import Base, get_async_session
from .config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Define User DB model (unchanged)
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
    
    # Google OAuth fields
    google_id = Column(String, unique=True, nullable=True)
    google_access_token = Column(String, nullable=True)
    google_refresh_token = Column(String, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)

    # Add relationships for categories, expenses, transactions
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
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

# Helper function to create JWT tokens
def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token for the given subject (user ID)
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    
    # Convert SecretStr to str if needed
    secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
    
    encoded_jwt = jwt.encode(
        payload, 
        secret_key, 
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt

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

async def send_email_via_sendgrid(to_email: str, subject: str, body: str) -> bool:
    """
    Send email using SendGrid API with proper headers to avoid spam (async version)
    """
    try:
        logger.info(f"Attempting to send email to {to_email}")
        
        # Validate email format
        if not to_email or "@" not in to_email:
            logger.error(f"Invalid email format: {to_email}")
            return False
        
        # Create the email message
        message = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        
        # Set reply-to address
        message.reply_to = settings.EMAIL_FROM
        
        # Initialize SendGrid client
        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        
        # Send the email in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            response = await loop.run_in_executor(executor, sg.send, message)
        
        if response.status_code == 202:
            logger.info(f"✅ Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"❌ Failed to send email. Status code: {response.status_code}")
            logger.error(f"Response body: {response.body}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Exception while sending email to {to_email}: {str(e)}")
        return False

# 4. User Manager with FIXED email handling
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info(f"User {user.email} has registered. Generating verification token…")

        try:
            # 1) Create a JWT verification token valid for 24 hours
            import jwt
            from datetime import datetime, timedelta

            expiry = datetime.utcnow() + timedelta(hours=24)
            payload = {
                "sub": str(user.id),
                "exp": expiry,
                "email": user.email,
                "type": "email_verification"
            }
            token = jwt.encode(
                payload,
                self.verification_token_secret,
                algorithm=settings.ALGORITHM,
            )

            logger.info(f"Verification token generated for {user.email}: {token[:10]}…")

            # 2) Send the email using your existing helper
            await self.on_after_request_verify(user, token, request)
            logger.info(f"Verification process completed for {user.email}")
            
        except Exception as e:
            logger.error(f"❌ Error during user registration verification for {user.email}: {str(e)}")

    async def verify(self, token: str, request: Optional[Request] = None) -> User:
        """Custom verify method with better error handling"""
        try:
            import jwt
            from datetime import datetime
            
            # Decode the token
            payload = jwt.decode(
                token,
                self.verification_token_secret,
                algorithms=[settings.ALGORITHM]
            )
            
            # Check if token is expired
            if datetime.utcnow().timestamp() > payload.get("exp", 0):
                logger.error("Verification token has expired")
                raise ValueError("Token has expired")
            
            # Get user ID from token
            user_id = payload.get("sub")
            if not user_id:
                logger.error("Invalid token: missing user ID")
                raise ValueError("Invalid token")
            
            # Get user from database
            user = await self.get(uuid.UUID(user_id))
            if not user:
                logger.error(f"User not found for ID: {user_id}")
                raise ValueError("User not found")
            
            # Check if already verified
            if user.is_verified:
                logger.info(f"User {user.email} is already verified")
                return user
            
            # Verify the user
            await self.user_db.update(user, {"is_verified": True})
            logger.info(f"User {user.email} verified successfully")
            
            # Call the after verify hook
            await self.on_after_verify(user, request)
            
            return user
            
        except jwt.ExpiredSignatureError:
            logger.error("JWT token has expired")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {str(e)}")
            raise ValueError("Invalid token")
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            raise ValueError("Verification failed")

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        logger.info(f"Verification requested for user {user.email}. Token: {token[:10]}...")
        
        # Use FRONTEND_URL for verification link
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        
        subject = "🔐 Verify your Budget Pay account"
        
        html_body = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verify Email - Budget Pay</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
                <div style="text-align: center; padding: 20px 0; border-bottom: 1px solid #eee;">
                    <h1 style="color: #007bff; margin: 0; font-size: 24px;">Budget Pay</h1>
                </div>
                
                <div style="padding: 30px 20px;">
                    <h2 style="color: #333; margin-bottom: 20px;">Welcome to Budget Pay!</h2>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        Hello <strong>{user_name}</strong>!
                    </p>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 30px;">
                        Thank you for signing up with Budget Pay. To complete your registration, 
                        please verify your email address by clicking the button below:
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verify_link}" 
                        style="background-color: #007bff; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 16px;">
                            Verify Email Address
                        </a>
                    </div>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 15px;">
                        Or copy and paste this link into your browser:
                    </p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; word-break: break-all; font-family: monospace; font-size: 14px; color: #666; margin-bottom: 30px;">
                        {verify_link}
                    </div>
                    
                    <div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; padding: 15px; margin-bottom: 20px;">
                        <p style="color: #155724; margin: 0; font-size: 14px;">
                            <strong>⏰ Important:</strong> This verification link will expire in 24 hours for security reasons.
                        </p>
                    </div>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        If you didn't create this account, please ignore this email and the account will remain unverified.
                    </p>
                </div>
                
                <div style="text-align: center; padding: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
                    <p style="margin: 0;">© 2025 Budget Pay Team. All rights reserved.</p>
                    <p style="margin: 5px 0 0 0;">Welcome aboard! 🎉</p>
                </div>
            </div>
        </body>
        </html>
        """.format(
            user_name=user.full_name or user.email.split('@')[0],
            verify_link=verification_url
        )
        
        success = await send_email_via_sendgrid(user.email, subject, html_body)
        if success:
            logger.info(f"✅ Verification email sent successfully to {user.email}")
        else:
            logger.error(f"❌ Failed to send verification email to {user.email}")

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        logger.info(f"Password reset requested for user {user.email}. Token: {token[:10]}...")
        
        # Use FRONTEND_URL for password reset (user interface)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        
        subject = "🔑 Reset your Budget Pay password"
        
        # FIXED: Proper HTML structure without f-string issues
        html_body = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reset Password - Budget Pay</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
                <div style="text-align: center; padding: 20px 0; border-bottom: 1px solid #eee;">
                    <h1 style="color: #007bff; margin: 0; font-size: 24px;">Budget Pay</h1>
                </div>
                
                <div style="padding: 30px 20px;">
                    <h2 style="color: #333; margin-bottom: 20px;">Password Reset Request</h2>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        Hello <strong>{user_name}</strong>!
                    </p>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 30px;">
                        We received a request to reset your password for your Budget Pay account. 
                        If you made this request, click the button below to set a new password:
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" 
                        style="background-color: #28a745; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; font-size: 16px;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 15px;">
                        Or copy and paste this link into your browser:
                    </p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; word-break: break-all; font-family: monospace; font-size: 14px; color: #666; margin-bottom: 30px;">
                        {reset_link}
                    </div>
                    
                    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin-bottom: 20px;">
                        <p style="color: #856404; margin: 0; font-size: 14px;">
                            <strong>⚠️ Important:</strong> This password reset link will expire in 1 hour for security reasons.
                        </p>
                    </div>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        <strong>Security Notice:</strong> If you didn't request this password reset, 
                        please ignore this email. Your password will remain unchanged and your account is secure.
                    </p>
                </div>
                
                <div style="text-align: center; padding: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
                    <p style="margin: 0;">© 2025 Budget Pay Team. All rights reserved.</p>
                    <p style="margin: 5px 0 0 0;">Need help? Contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """.format(
            user_name=user.full_name or user.email.split('@')[0],
            reset_link=reset_url
        )
        
        success = await send_email_via_sendgrid(user.email, subject, html_body)
        if success:
            logger.info(f"✅ Password reset email sent successfully to {user.email}")
        else:
            logger.error(f"❌ Failed to send password reset email to {user.email}")

    async def on_after_verify(self, user: User, request: Optional[Request] = None):
        logger.info(f"User {user.email} has been verified successfully! 🎉")

    async def on_after_reset_password(self, user: User, request: Optional[Request] = None):
        logger.info(f"Password reset completed for user {user.email}")

# 4. User Database
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)

# 5. User Manager dependency
async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

# 6. Authentication - FIXED: Correct tokenUrl to match your API structure
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    # Convert SecretStr to str if needed
    secret_key = str(settings.SECRET_KEY) if hasattr(settings.SECRET_KEY, "get_secret_value") else settings.SECRET_KEY
    
    # Use the ACCESS_TOKEN_EXPIRE_MINUTES from settings (10080 minutes = 7 days)
    return JWTStrategy(
        secret=secret_key, 
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_audience=["fastapi-users:auth"]  # Explicitly set audience
    )

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