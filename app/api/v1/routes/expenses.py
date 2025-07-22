# app/api/v1/routes/expenses.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, List
import uuid
from datetime import datetime, timedelta
from enum import Enum

from app.models.category import Category
from app.models.transaction import Transaction
from app.api.deps import get_current_user
from app.core.database import get_async_session
from app.core.auth import User

router = APIRouter(prefix="/expenses", tags=["expenses"])

class TimePeriod(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"

def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default

@router.get("/overview/budget", response_model=Dict[str, Any])
async def get_expense_overview(
    time_period: TimePeriod = Query(TimePeriod.monthly, description="Time period for budget calculations"),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Get an overview of expenses with allocated, spent, and remaining amounts.
    Returns data for the top cards and category-wise breakdown.
    """
    # Get user's monthly income and savings goal
    monthly_income_val = getattr(user, 'monthly_income', None)
    savings_goal_val = getattr(user, 'savings_goal_amount', None)
    monthly_income = float(monthly_income_val) if monthly_income_val and isinstance(monthly_income_val, str) and monthly_income_val.strip() else 0
    savings_goal = float(savings_goal_val) if savings_goal_val and isinstance(savings_goal_val, str) and savings_goal_val.strip() else 0
    
    # Calculate time period multiplier and date range
    now = datetime.now()
    
    if time_period == TimePeriod.daily:
        multiplier = 1/30  # Assuming 30 days in a month
        start_date = datetime(now.year, now.month, now.day)
        end_date = start_date + timedelta(days=1)
        period_label = "Daily"
    elif time_period == TimePeriod.weekly:
        multiplier = 1/4.33  # Approximately 4.33 weeks in a month
        # Start from the beginning of the current week (Monday)
        start_date = now - timedelta(days=now.weekday())
        start_date = datetime(start_date.year, start_date.month, start_date.day)
        end_date = start_date + timedelta(days=7)
        period_label = "Weekly"
    elif time_period == TimePeriod.yearly:
        multiplier = 12  # 12 months in a year
        start_date = datetime(now.year, 1, 1)
        end_date = datetime(now.year + 1, 1, 1)
        period_label = "Yearly"
    else:  # monthly (default)
        multiplier = 1
        start_date = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1)
        else:
            end_date = datetime(now.year, now.month + 1, 1)
        period_label = "Monthly"
    
    # Calculate allocated budget (income - savings goal) for the selected time period
    allocated_budget = (monthly_income - savings_goal) * multiplier
    
    # Get all categories for the user
    result = await db.execute(select(Category).where(Category.user_id == user.id))
    categories = result.scalars().all()
    
    # Get all transactions for the user within the date range
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date < end_date
        )
    )
    transactions = result.scalars().all()
    
    # Calculate total spent amount
    total_spent = sum(transaction.amount for transaction in transactions)
    
    # Calculate remaining budget
    remaining_budget = allocated_budget - total_spent
    
    # Prepare category-wise data
    dynamic_categories = []
    fixed_categories = []
    
    for category in categories:
        # Calculate allocated amount for this category based on percentage
        percentage = safe_float(category.custom_percentage) if category.custom_percentage is not None else safe_float(category.default_percentage)
        category_allocated = safe_float(allocated_budget) * (percentage / 100)
        
        # Calculate spent amount for this category
        category_spent = sum(
            safe_float(transaction.amount) for transaction in transactions 
            if transaction.category_id == category.id
        )
        
        # Calculate remaining amount
        category_remaining = category_allocated - category_spent
        
        # Determine status
        status = "On Track"
        if category_spent > category_allocated:
            status = "Over Budget"
        elif category_spent >= category_allocated * 0.9:
            status = "Near Limit"
        
        # Prepare category data based on whether it's a fixed or dynamic category
        category_data = {
            "id": str(category.id),
            "name": category.name,
            "allocated": round(category_allocated, 2),
            "spent": round(category_spent, 2),
            "remaining": round(category_remaining, 2),
            "status": status,
        }
        
        if category.is_fixed:
            # For fixed categories, no progress percentage is needed
            fixed_categories.append(category_data)
        else:
            # For dynamic categories, include progress percentage
            progress_percentage = min(100.0, (category_spent / category_allocated * 100.0) if category_allocated > 0 else 0.0)
            category_data["progress_percentage"] = round(progress_percentage, 2)
            dynamic_categories.append(category_data)
    
    return {
        "summary": {
            "time_period": time_period,
            "period_label": period_label,
            "allocated": round(safe_float(allocated_budget), 2),
            "spent": round(safe_float(total_spent), 2),
            "remaining": round(safe_float(remaining_budget), 2)
        },
        "dynamic_categories": dynamic_categories,
        "fixed_categories": fixed_categories
    }
