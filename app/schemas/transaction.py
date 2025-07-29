# app/schemas/transaction.py
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class TransactionBase(BaseModel):
    description: str = Field(..., description="E.g. Grocery at Costco")
    amount: float
    category_id: Optional[uuid.UUID] = None
    transaction_date: datetime = Field(..., description="ISO 8601 date/time of transaction")

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    description: Optional[str]
    amount: Optional[float]
    category_id: Optional[uuid.UUID]
    transaction_date: Optional[datetime]

class TransactionRead(TransactionBase):
    id: uuid.UUID
    user_id: uuid.UUID

    class Config:
        orm_mode = True
