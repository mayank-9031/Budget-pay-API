# app/schemas/user.py
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

# Public fields returned on GET /users/me
class UserRead(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str]
    monthly_income: Optional[float]
    savings_goal_amount: Optional[float]
    savings_goal_deadline: Optional[datetime]
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True

# Fields accepted on PATCH /users/me
class UserUpdate(BaseModel):
    full_name: Optional[str]
    monthly_income: Optional[float]
    savings_goal_amount: Optional[float]
    savings_goal_deadline: Optional[datetime]

    class Config:
        from_attributes = True

class GoogleAuthRequest(BaseModel):
    redirect_uri: Optional[str] = None

class GoogleAuthResponse(BaseModel):
    authorization_url: str

class GoogleCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None
    error: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None

class UserProfile(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True
    is_verified: bool = True
