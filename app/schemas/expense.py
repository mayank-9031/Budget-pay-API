# app/schemas/expense.py
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from app.models.expense import FrequencyType

class ExpenseBase(BaseModel):
    name: str = Field(..., description="Expense name, e.g. Rent, Netflix")
    amount: float = Field(..., description="Amount per occurrence")
    category_id: Optional[uuid.UUID] = None
    frequency_type: FrequencyType = FrequencyType.one_time
    interval_days: Optional[int] = None
    next_due_date: Optional[datetime] = None
    is_active: Optional[bool] = True

class ExpenseCreate(ExpenseBase):
    pass

class ExpenseUpdate(BaseModel):
    name: Optional[str]
    amount: Optional[float]
    category_id: Optional[uuid.UUID]
    frequency_type: Optional[FrequencyType]
    interval_days: Optional[int]
    next_due_date: Optional[datetime]
    is_active: Optional[bool]

class ExpenseRead(ExpenseBase):
    id: uuid.UUID
    user_id: uuid.UUID

    class Config:
        orm_mode = True
