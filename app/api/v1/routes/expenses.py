# app/api/v1/routes/expenses.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timedelta
from enum import Enum

from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.crud.expense import (
    create_expense_for_user,
    get_expenses_for_user,
    get_expense_by_id,
    update_expense,
    delete_expense,
)
from app.core.database import get_async_session
from app.core.auth import current_active_user, User
from app.models.category import Category
from app.models.transaction import Transaction
from app.api.deps import get_current_user

router = APIRouter(prefix="/expenses", tags=["expenses"])

class TimePeriod(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"

@router.get("", response_model=List[ExpenseRead])
async def read_expenses(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await get_expenses_for_user(user.id, db)

@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense(
    ex_in: ExpenseCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await create_expense_for_user(user.id, ex_in, db)

@router.get("/{expense_id}", response_model=ExpenseRead)
async def read_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return ex

@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense_endpoint(
    expense_id: uuid.UUID,
    ex_in: ExpenseUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return await update_expense(ex, ex_in, db)

@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_endpoint(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    await delete_expense(ex, db)
    return None

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
    monthly_income = float(user.monthly_income) if user.monthly_income else 0
    savings_goal = float(user.savings_goal_amount) if user.savings_goal_amount else 0
    
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
    category_data = []
    
    for category in categories:
        # Calculate allocated amount for this category based on percentage
        percentage = category.custom_percentage if category.custom_percentage is not None else category.default_percentage
        category_allocated = allocated_budget * (percentage / 100)
        
        # Calculate spent amount for this category
        category_spent = sum(
            transaction.amount for transaction in transactions 
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
        
        # Calculate progress percentage (capped at 100%)
        progress_percentage = min(100, (category_spent / category_allocated * 100) if category_allocated > 0 else 0)
        
        category_data.append({
            "id": str(category.id),
            "name": category.name,
            "allocated": round(category_allocated, 2),
            "spent": round(category_spent, 2),
            "remaining": round(category_remaining, 2),
            "status": status,
            "progress_percentage": round(progress_percentage, 2)
        })
    
    return {
        "summary": {
            "time_period": time_period,
            "period_label": period_label,
            "allocated": round(allocated_budget, 2),
            "spent": round(total_spent, 2),
            "remaining": round(remaining_budget, 2)
        },
        "categories": category_data
    }
