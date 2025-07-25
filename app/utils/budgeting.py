# app/utils/budgeting.py
import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.core.auth import User

async def calculate_goal_progress(
    user: User,
    period: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Calculate savings goal progress based on period (daily, weekly, monthly, yearly)
    with journey start date consideration
    """
    # Validate required user fields
    if not user.monthly_income or not user.savings_goal_amount:
        return {
            "target_amount": 0.0,
            "saved_amount": 0.0,
            "progress_percentage": 0.0,
            "status": "Not Set",
            "period_end_date": datetime.now(),
            "percentage_of_income": 0.0,
            "remaining_amount": 0.0,
            "journey_start_date": None,
            "days_in_journey": 0
        }
    
    # Convert strings to float
    monthly_income = float(user.monthly_income)
    savings_goal_amount = float(user.savings_goal_amount)
    
    # Get journey start date
    today = datetime.now().date()
    journey_start = await get_journey_start_date(db, user.id)
    
    # If no journey start date found, use today as start date
    if not journey_start:
        journey_start = today
    
    # Get transactions based on period
    transactions = await get_period_transactions(db, user.id, period, today, journey_start)
    
    # Calculate period expenses (sum of transaction amounts)
    period_expenses = sum(transaction.amount for transaction in transactions)
    
    # Calculate goal progress based on period with journey consideration
    if period == "daily":
        result = calculate_daily_goal_progress(monthly_income, savings_goal_amount, period_expenses, today, journey_start)
    elif period == "weekly":
        result = calculate_weekly_goal_progress(monthly_income, savings_goal_amount, period_expenses, today, journey_start)
    elif period == "yearly":
        result = await calculate_yearly_goal_progress(monthly_income, savings_goal_amount, user.id, db, today, journey_start)
    else:  # Default to monthly
        result = calculate_monthly_goal_progress(monthly_income, savings_goal_amount, period_expenses, today, journey_start)
    
    # Determine status based on progress
    result["status"] = determine_status(result["progress_percentage"], period, today, journey_start)
    
    # Calculate percentage of income
    result["percentage_of_income"] = (savings_goal_amount / monthly_income) * 100 if monthly_income > 0 else 0
    
    # Add journey information
    result["journey_start_date"] = journey_start
    result["days_in_journey"] = (today - journey_start).days + 1
    
    return result

async def get_period_transactions(
    db: AsyncSession, 
    user_id: str, 
    period: str, 
    today: date, 
    journey_start: date
) -> List[Transaction]:
    """Get transactions for the specified period, considering journey start date"""
    period_start = None
    
    if period == "daily":
        # For daily: only get today's transactions if journey started today or before
        if journey_start <= today:
            period_start = today
        else:
            return []  # Journey hasn't started yet
    elif period == "weekly":
        # Get transactions for this week (starting Monday) but not before journey start
        week_start = today - timedelta(days=today.weekday())
        period_start = max(week_start, journey_start)
    elif period == "monthly":
        # Get transactions for this month but not before journey start
        month_start = date(today.year, today.month, 1)
        period_start = max(month_start, journey_start)
    elif period == "yearly":
        # Get transactions for this year but not before journey start
        year_start = date(today.year, 1, 1)
        period_start = max(year_start, journey_start)
    
    if not period_start:
        return []
    
    # Convert to datetime for query
    start_datetime = datetime.combine(period_start, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())
    
    # Query transactions
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= start_datetime,
            Transaction.transaction_date <= end_datetime
        )
    )
    
    return result.scalars().all()

def calculate_daily_goal_progress(
    monthly_income: float, 
    monthly_savings_goal: float, 
    daily_expenses: float, 
    today: date,
    journey_start: date
) -> Dict[str, Any]:
    """Calculate daily savings goal progress considering journey start"""
    
    # If journey hasn't started today, return zero progress
    if journey_start > today:
        return {
            "target_amount": 0.0,
            "saved_amount": 0.0,
            "progress_percentage": 0.0,
            "period_end_date": datetime.combine(today, datetime.max.time()),
            "remaining_amount": 0.0
        }
    
    # Target amount for the day
    daily_target = monthly_savings_goal / 30
    
    # Daily income
    daily_income = monthly_income / 30
    
    # If journey started today, calculate based on full day
    # If journey started before today, also calculate based on full day (today's progress)
    daily_saved = daily_income - daily_expenses
    
    # Calculate progress percentage
    progress_percentage = (daily_saved / daily_target) * 100 if daily_target > 0 else 0
    
    # Calculate period end date (end of today)
    period_end_date = datetime.combine(today, datetime.max.time())
    
    # Calculate remaining amount
    remaining_amount = max(0, daily_target - daily_saved)
    
    return {
        "target_amount": daily_target,
        "saved_amount": daily_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount
    }

def calculate_weekly_goal_progress(
    monthly_income: float, 
    monthly_savings_goal: float, 
    weekly_expenses: float, 
    today: date,
    journey_start: date
) -> Dict[str, Any]:
    """Calculate weekly savings goal progress considering journey start"""
    
    # Get week boundaries
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    
    # Determine effective start date for this week
    effective_start = max(week_start, journey_start)
    
    # If journey hasn't started this week, return zero progress
    if effective_start > today:
        return {
            "target_amount": 0.0,
            "saved_amount": 0.0,
            "progress_percentage": 0.0,
            "period_end_date": datetime.combine(week_end, datetime.max.time()),
            "remaining_amount": 0.0
        }
    
    # Calculate days in journey for this week
    days_in_journey_this_week = (today - effective_start).days + 1
    
    # Proportional target and income based on journey days
    weekly_target = monthly_savings_goal / 4
    proportional_target = (weekly_target / 7) * days_in_journey_this_week
    
    weekly_income = monthly_income / 4
    proportional_income = (weekly_income / 7) * days_in_journey_this_week
    
    # Saved amount for the journey period in this week
    weekly_saved = proportional_income - weekly_expenses
    
    # Calculate progress percentage
    progress_percentage = (weekly_saved / proportional_target) * 100 if proportional_target > 0 else 0
    
    # Calculate period end date (end of week - Sunday)
    period_end_date = datetime.combine(week_end, datetime.max.time())
    
    # Calculate remaining amount
    remaining_amount = max(0, proportional_target - weekly_saved)
    
    return {
        "target_amount": proportional_target,
        "saved_amount": weekly_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount
    }

def calculate_monthly_goal_progress(
    monthly_income: float, 
    monthly_savings_goal: float, 
    monthly_expenses: float, 
    today: date,
    journey_start: date
) -> Dict[str, Any]:
    """Calculate monthly savings goal progress considering journey start"""
    
    # Get month boundaries  
    month_start = date(today.year, today.month, 1)
    last_day_of_month = calendar.monthrange(today.year, today.month)[1]
    month_end = date(today.year, today.month, last_day_of_month)
    
    # Determine effective start date for this month
    effective_start = max(month_start, journey_start)
    
    # If journey hasn't started this month, return zero progress
    if effective_start > today:
        return {
            "target_amount": 0.0,
            "saved_amount": 0.0,
            "progress_percentage": 0.0,
            "period_end_date": datetime(today.year, today.month, last_day_of_month, 23, 59, 59),
            "remaining_amount": 0.0
        }
    
    # Calculate days in journey for this month
    days_in_journey_this_month = (today - effective_start).days + 1
    
    # Proportional target and income based on journey days
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    proportional_target = (monthly_savings_goal / days_in_month) * days_in_journey_this_month
    proportional_income = (monthly_income / days_in_month) * days_in_journey_this_month
    
    # Saved amount for the journey period in this month
    monthly_saved = proportional_income - monthly_expenses
    
    # Calculate progress percentage
    progress_percentage = (monthly_saved / proportional_target) * 100 if proportional_target > 0 else 0
    
    # Calculate period end date (end of month)
    period_end_date = datetime(today.year, today.month, last_day_of_month, 23, 59, 59)
    
    # Calculate remaining amount
    remaining_amount = max(0, proportional_target - monthly_saved)
    
    return {
        "target_amount": proportional_target,
        "saved_amount": monthly_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount
    }

async def calculate_yearly_goal_progress(
    monthly_income: float, 
    monthly_savings_goal: float, 
    user_id: str, 
    db: AsyncSession,
    today: date,
    journey_start: date
) -> Dict[str, Any]:
    """Calculate yearly savings goal progress considering journey start"""
    
    # Get year boundaries
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    
    # Determine effective start date for this year
    effective_start = max(year_start, journey_start)
    
    # If journey hasn't started this year, return zero progress
    if effective_start > today:
        return {
            "target_amount": 0.0,
            "saved_amount": 0.0,
            "progress_percentage": 0.0,
            "period_end_date": datetime(today.year, 12, 31, 23, 59, 59),
            "remaining_amount": 0.0,
            "adjusted_monthly_goal": monthly_savings_goal
        }
    
    # Calculate days in journey for this year
    days_in_journey_this_year = (today - effective_start).days + 1
    
    # Calculate total days in year
    days_in_year = 366 if calendar.isleap(today.year) else 365
    
    # Proportional yearly target based on journey days
    yearly_target = monthly_savings_goal * 12
    proportional_yearly_target = (yearly_target / days_in_year) * days_in_journey_this_year
    
    # Calculate proportional yearly income
    yearly_income = monthly_income * 12
    proportional_yearly_income = (yearly_income / days_in_year) * days_in_journey_this_year
    
    # Get all transactions since journey start (but within this year)
    transactions = await get_period_transactions(db, user_id, "yearly", today, journey_start)
    total_expenses = sum(transaction.amount for transaction in transactions)
    
    # Calculate total saved amount
    total_saved = proportional_yearly_income - total_expenses
    
    # Calculate progress percentage
    progress_percentage = (total_saved / proportional_yearly_target) * 100 if proportional_yearly_target > 0 else 0
    
    # Calculate remaining months and adjusted monthly goal
    remaining_days_in_year = (year_end - today).days
    remaining_months = remaining_days_in_year / 30.44  # Average days per month
    
    if remaining_months > 0:
        remaining_target = proportional_yearly_target - total_saved
        adjusted_monthly_goal = max(0, remaining_target / remaining_months)
    else:
        adjusted_monthly_goal = monthly_savings_goal
    
    # Calculate period end date (end of year)
    period_end_date = datetime(today.year, 12, 31, 23, 59, 59)
    
    # Calculate remaining amount
    remaining_amount = max(0, proportional_yearly_target - total_saved)
    
    return {
        "target_amount": proportional_yearly_target,
        "saved_amount": total_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount,
        "adjusted_monthly_goal": adjusted_monthly_goal
    }

async def get_journey_start_date(db: AsyncSession, user_id: str) -> Optional[date]:
    """Get the first transaction date for the user or user registration date"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date)
        .limit(1)
    )
    
    first_transaction = result.scalar_one_or_none()
    if first_transaction and first_transaction.transaction_date:
        return first_transaction.transaction_date.date()
    
    # If no transactions found, you might want to use user registration date
    # For now, return None to use today as start date
    return None

async def get_month_transactions(db: AsyncSession, user_id: str, start_date: date, end_date: date) -> List[Transaction]:
    """Get transactions for a specific month"""
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time())
    
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= start_datetime,
            Transaction.transaction_date < end_datetime
        )
    )
    
    return result.scalars().all()

def get_months_stats(start_date: date, today: date) -> Tuple[int, int]:
    """Calculate months completed and remaining in the year"""
    months_completed = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    months_remaining = 12 - months_completed if months_completed < 12 else 0
    
    return months_completed, months_remaining

def determine_status(progress_percentage: float, period: str, today: date, journey_start: date) -> str:
    """Determine the status based on progress percentage and time elapsed in period since journey start"""
    if progress_percentage >= 100:
        return "Goal Achieved"
    
    # Calculate time elapsed percentage based on period and journey start
    if period == "daily":
        # If journey started today, check current hour progress
        if journey_start == today:
            elapsed_percentage = datetime.now().hour / 24 * 100
        else:
            elapsed_percentage = 100  # Full day has passed
    elif period == "weekly":
        # Days elapsed in the week since journey start
        week_start = today - timedelta(days=today.weekday())
        effective_start = max(week_start, journey_start)
        days_elapsed = (today - effective_start).days + 1
        elapsed_percentage = min(days_elapsed / 7 * 100, 100)
    elif period == "monthly":
        # Days elapsed in the month since journey start
        month_start = date(today.year, today.month, 1)
        effective_start = max(month_start, journey_start)
        days_elapsed = (today - effective_start).days + 1
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        elapsed_percentage = min(days_elapsed / days_in_month * 100, 100)
    else:  # yearly
        # Days elapsed in the year since journey start
        year_start = date(today.year, 1, 1)
        effective_start = max(year_start, journey_start)
        days_elapsed = (today - effective_start).days + 1
        days_in_year = 366 if calendar.isleap(today.year) else 365
        elapsed_percentage = min(days_elapsed / days_in_year * 100, 100)
    
    # Determine status based on progress and time elapsed
    if progress_percentage >= 75:
        return "On Track"
    elif progress_percentage >= 50:
        return "In Progress"
    elif elapsed_percentage > 50 and progress_percentage < 25:
        return "Behind Target"
    else:
        return "In Progress"