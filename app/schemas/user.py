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
        orm_mode = True

# Fields accepted on PATCH /users/me
class UserUpdate(BaseModel):
    full_name: Optional[str]
    monthly_income: Optional[float]
    savings_goal_amount: Optional[float]
    savings_goal_deadline: Optional[datetime]

    class Config:
        orm_mode = True
