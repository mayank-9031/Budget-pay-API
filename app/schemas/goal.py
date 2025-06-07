# app/schemas/goal.py
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class GoalBase(BaseModel):
    target_amount: float
    deadline: datetime

class GoalCreate(GoalBase):
    pass

class GoalUpdate(BaseModel):
    target_amount: Optional[float]
    deadline: Optional[datetime]
    saved_amount: Optional[float]
    is_active: Optional[bool]

class GoalRead(GoalBase):
    id: uuid.UUID
    user_id: uuid.UUID
    saved_amount: float
    is_active: bool

    class Config:
        orm_mode = True
