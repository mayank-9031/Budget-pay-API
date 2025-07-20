# app/schemas/goal.py
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime

class GoalProgressRequest(BaseModel):
    period: Literal["daily", "weekly", "monthly", "yearly"] = "monthly"

class GoalProgressResponse(BaseModel):
    target_amount: float
    saved_amount: float
    progress_percentage: float
    status: str
    period_end_date: datetime
    percentage_of_income: float
    remaining_amount: float