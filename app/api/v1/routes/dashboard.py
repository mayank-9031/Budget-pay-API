# app/api/v1/routes/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
from enum import Enum
from collections import defaultdict

from app.core.database import get_async_session
from app.core.auth import current_active_user, User
from app.crud.category import get_categories_for_user
from app.crud.expense import get_expenses_for_user
from app.crud.transaction import get_transactions_for_user
from app.utils.budgeting import allocate_budget, calculate_daily_budget, calculate_monthly_recurring_total
from app.models.category import Category
from app.models.transaction import Transaction
from app.api.deps import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

class TimePeriod(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"

@router.get("/summary")
async def get_dashboard_summary(
    time_period: TimePeriod = Query(TimePeriod.monthly, description="Time period for budget calculations"),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> Dict:
    """
    Returns a comprehensive dashboard summary with data for all UI components:
    - Cards: income, remaining, spent, savings progress
    - Charts: spending trends, category allocation, daily spending, top spending categories
    - Tables: budget health, category health
    """
    monthly_income = float(user.monthly_income) if user.monthly_income else 0
    savings_goal = float(user.savings_goal_amount) if user.savings_goal_amount else 0

    now = datetime.now()

    if time_period == TimePeriod.daily:
        multiplier = 1/30
        start_date = datetime(now.year, now.month, now.day)
        end_date = start_date + timedelta(days=1)
        period_label = "Daily"
    elif time_period == TimePeriod.weekly:
        multiplier = 1/4.33
        start_date = now - timedelta(days=now.weekday())
        start_date = datetime(start_date.year, start_date.month, start_date.day)
        end_date = start_date + timedelta(days=7)
        period_label = "Weekly"
    elif time_period == TimePeriod.yearly:
        multiplier = 12
        start_date = datetime(now.year, 1, 1)
        end_date = datetime(now.year + 1, 1, 1)
        period_label = "Yearly"
    else:
        multiplier = 1
        start_date = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1)
        else:
            end_date = datetime(now.year, now.month + 1, 1)
        period_label = "Monthly"

    allocated_budget = (monthly_income - savings_goal) * multiplier

    result = await db.execute(select(Category).where(Category.user_id == user.id))
    categories = result.scalars().all()

    result = await db.execute(select(Transaction).where(Transaction.user_id == user.id))
    all_transactions = result.scalars().all()

    period_transactions = [
        tx for tx in all_transactions 
        if tx.transaction_date >= start_date and tx.transaction_date < end_date
    ]

    total_spent = sum(tx.amount for tx in period_transactions)
    remaining_budget = allocated_budget - total_spent

    savings_progress_percentage = 0
    if savings_goal > 0:
        if time_period == TimePeriod.monthly:
            days_in_month = (end_date - start_date).days
            days_passed = (now - start_date).days
            actual_savings = max(0, monthly_income - total_spent)
            savings_progress_percentage = min(100, (actual_savings / savings_goal * 100)) if savings_goal > 0 else 0
        else:
            actual_savings = max(0, allocated_budget - total_spent)
            period_savings_goal = savings_goal * multiplier
            savings_progress_percentage = min(100, (actual_savings / period_savings_goal * 100)) if period_savings_goal > 0 else 0

    category_data = []
    category_allocation = {}
    spent_per_category = defaultdict(float)

    for tx in period_transactions:
        if tx.category_id:
            spent_per_category[tx.category_id] += tx.amount

    for category in categories:
        if category.custom_percentage is not None:
            percentage = category.custom_percentage
        else:
            percentage = category.default_percentage
        category_allocated = allocated_budget * (percentage / 100)
        category_allocation[category.id] = category_allocated

        category_spent = spent_per_category.get(category.id, 0)
        category_remaining = category_allocated - category_spent

        status = "Good"
        if category_spent > category_allocated:
            status = "Over Budget"
        elif category_spent >= category_allocated * 0.9:
            status = "Near Limit"

        progress_percentage = min(100, (category_spent / category_allocated * 100) if category_allocated > 0 else 0)

        category_data.append({
            "id": str(category.id),
            "name": category.name,
            "allocated": round(category_allocated, 2),
            "spent": round(category_spent, 2),
            "remaining": round(category_remaining, 2),
            "status": status,
            "progress_percentage": round(progress_percentage, 2),
            "color": f"#{hash(category.name) % 0xffffff:06x}"
        })

    category_data.sort(key=lambda x: x["spent"], reverse=True)
    top_spending_categories = category_data[:5]

    spending_trends = []

    if time_period == TimePeriod.daily:
        hourly_spending = defaultdict(float)
        for tx in period_transactions:
            hour = tx.transaction_date.hour
            hourly_spending[hour] += tx.amount

        for hour in range(24):
            spending_trends.append({
                "label": f"{hour}:00",
                "amount": round(hourly_spending.get(hour, 0), 2)
            })

    elif time_period == TimePeriod.weekly:
        daily_spending = defaultdict(float)
        week_start = start_date

        for i in range(7):
            day = week_start + timedelta(days=i)
            day_label = day.strftime("%a")
            daily_spending[day_label] = sum(
                tx.amount for tx in period_transactions 
                if tx.transaction_date.date() == day.date()
            )

        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            spending_trends.append({
                "label": day_name,
                "amount": round(daily_spending.get(day_name, 0), 2)
            })

    elif time_period == TimePeriod.monthly:
        weekly_spending = defaultdict(float)
        month_start = start_date

        for week_num in range(1, 5):
            week_start = month_start + timedelta(days=(week_num-1)*7)
            week_end = week_start + timedelta(days=7)

            weekly_spending[f"Week {week_num}"] = sum(
                tx.amount for tx in period_transactions 
                if week_start <= tx.transaction_date < week_end
            )

        for week_num in range(1, 5):
            spending_trends.append({
                "label": f"Week {week_num}",
                "amount": round(weekly_spending.get(f"Week {week_num}", 0), 2)
            })

    else:
        monthly_spending = defaultdict(float)

        for month_num in range(1, 13):
            if month_num == 12:
                month_start = datetime(now.year, month_num, 1)
                month_end = datetime(now.year + 1, 1, 1)
            else:
                month_start = datetime(now.year, month_num, 1)
                month_end = datetime(now.year, month_num + 1, 1)

            monthly_spending[month_num] = sum(
                tx.amount for tx in all_transactions 
                if month_start <= tx.transaction_date < month_end
            )

        for month_num in range(1, 13):
            month_name = datetime(2000, month_num, 1).strftime("%b")
            spending_trends.append({
                "label": month_name,
                "amount": round(monthly_spending.get(month_num, 0), 2)
            })

    daily_spending = []
    for i in range(7, 0, -1):
        day_date = now.date() - timedelta(days=i-1)
        day_amount = sum(
            tx.amount for tx in all_transactions 
            if tx.transaction_date.date() == day_date
        )
        daily_spending.append({
            "label": day_date.strftime("%b %d"),
            "amount": round(day_amount, 2)
        })

    category_allocation_data = []
    for cat in category_data:
        category_allocation_data.append({
            "name": cat["name"],
            "allocated": cat["allocated"],
            "color": cat["color"]
        })

    total_transactions = len(period_transactions)
    avg_transaction_amount = round(total_spent / total_transactions, 2) if total_transactions > 0 else 0
    categories_used = len(set(tx.category_id for tx in period_transactions if tx.category_id))

    return {
        "cards": {
            "time_period": time_period,
            "period_label": period_label,
            "income": round(monthly_income * multiplier, 2),
            "spent": round(total_spent, 2),
            "remaining": round(remaining_budget, 2),
            "savings_progress": {
                "percentage": round(savings_progress_percentage, 2),
                "saved_amount": round(max(0, monthly_income * multiplier - total_spent), 2),
                "goal_amount": round(savings_goal * multiplier, 2)
            }
        },
        "spending_trends": spending_trends,
        "category_allocation": category_allocation_data,
        "daily_spending": daily_spending,
        "top_spending_categories": top_spending_categories,
        "quick_stats": {
            "total_transactions": total_transactions,
            "avg_transaction_amount": avg_transaction_amount,
            "categories_used": categories_used
        },
        "category_health": category_data
    }
    