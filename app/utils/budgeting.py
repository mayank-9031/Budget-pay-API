# app/utils/budgeting.py
import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple
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
            "remaining_amount": 0.0
        }
    
    # Convert strings to float
    monthly_income = float(user.monthly_income)
    savings_goal_amount = float(user.savings_goal_amount)
    
    # Get transaction history
    today = datetime.now().date()
    
    # Get transactions based on period
    transactions = await get_period_transactions(db, user.id, period, today)
    
    # Calculate period expenses (sum of transaction amounts)
    period_expenses = sum(transaction.amount for transaction in transactions)
    
    # Calculate goal progress based on period
    if period == "daily":
        result = calculate_daily_goal_progress(monthly_income, savings_goal_amount, period_expenses, today)
    elif period == "weekly":
        result = calculate_weekly_goal_progress(monthly_income, savings_goal_amount, period_expenses, today)
    elif period == "yearly":
        result = await calculate_yearly_goal_progress(monthly_income, savings_goal_amount, user.id, db, today)
    else:  # Default to monthly
        result = calculate_monthly_goal_progress(monthly_income, savings_goal_amount, period_expenses, today)
    
    # Determine status based on progress
    result["status"] = determine_status(result["progress_percentage"], period, today)
    
    # Calculate percentage of income
    result["percentage_of_income"] = (savings_goal_amount / monthly_income) * 100 if monthly_income > 0 else 0
    
    return result

async def get_period_transactions(db: AsyncSession, user_id: str, period: str, today: date) -> List[Transaction]:
    """Get transactions for the specified period"""
    start_date = None
    
    if period == "daily":
        # Get transactions for today
        start_date = today
    elif period == "weekly":
        # Get transactions for this week (starting Monday)
        start_date = today - timedelta(days=today.weekday())
    elif period == "monthly":
        # Get transactions for this month
        start_date = date(today.year, today.month, 1)
    elif period == "yearly":
        # Get transactions for this year
        start_date = date(today.year, 1, 1)
    
    # Convert to datetime for query
    start_datetime = datetime.combine(start_date, datetime.min.time())
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

def calculate_daily_goal_progress(monthly_income: float, monthly_savings_goal: float, daily_expenses: float, today: date) -> Dict[str, Any]:
    """Calculate daily savings goal progress"""
    # Target amount for the day
    daily_target = monthly_savings_goal / 30
    
    # Daily income
    daily_income = monthly_income / 30
    
    # Saved amount for the day
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

def calculate_weekly_goal_progress(monthly_income: float, monthly_savings_goal: float, weekly_expenses: float, today: date) -> Dict[str, Any]:
    """Calculate weekly savings goal progress"""
    # Target amount for the week
    weekly_target = monthly_savings_goal / 4
    
    # Weekly income
    weekly_income = monthly_income / 4
    
    # Days elapsed in the week (1-7, Monday is 0)
    days_elapsed = today.weekday() + 1
    
    # Available budget based on elapsed days
    available_budget = (weekly_income / 7) * days_elapsed
    
    # Saved amount for the week
    weekly_saved = available_budget - weekly_expenses
    
    # Calculate progress percentage
    progress_percentage = (weekly_saved / weekly_target) * 100 if weekly_target > 0 else 0
    
    # Calculate period end date (end of week - Sunday)
    days_until_sunday = 6 - today.weekday()
    period_end_date = datetime.combine(today + timedelta(days=days_until_sunday), datetime.max.time())
    
    # Calculate remaining amount
    remaining_amount = max(0, weekly_target - weekly_saved)
    
    return {
        "target_amount": weekly_target,
        "saved_amount": weekly_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount
    }

def calculate_monthly_goal_progress(monthly_income: float, monthly_savings_goal: float, monthly_expenses: float, today: date) -> Dict[str, Any]:
    """Calculate monthly savings goal progress"""
    # Target amount for the month
    monthly_target = monthly_savings_goal
    
    # Days elapsed in the month
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    
    # Available budget based on elapsed days
    available_budget = (monthly_income / days_in_month) * days_elapsed
    
    # Saved amount for the month
    monthly_saved = available_budget - monthly_expenses
    
    # Calculate progress percentage
    progress_percentage = (monthly_saved / monthly_target) * 100 if monthly_target > 0 else 0
    
    # Calculate period end date (end of month)
    last_day_of_month = calendar.monthrange(today.year, today.month)[1]
    period_end_date = datetime(today.year, today.month, last_day_of_month, 23, 59, 59)
    
    # Calculate remaining amount
    remaining_amount = max(0, monthly_target - monthly_saved)
    
    return {
        "target_amount": monthly_target,
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
    today: date
) -> Dict[str, Any]:
    """Calculate yearly savings goal progress with adjustments for past performance"""
    # Find journey start date (first transaction date or beginning of year)
    journey_start = await get_journey_start_date(db, user_id)
    if not journey_start:
        journey_start = date(today.year, 1, 1)
    
    # Calculate months completed and remaining
    months_completed, months_remaining = get_months_stats(journey_start, today)
    
    # Yearly target
    yearly_target = monthly_savings_goal * 12
    
    # Track monthly performance for each completed month
    total_deficit = 0
    total_saved = 0
    
    # Process each completed month
    current_month = journey_start.replace(day=1)
    while current_month < date(today.year, today.month, 1):
        # Get next month for range calculation
        if current_month.month == 12:
            next_month = date(current_month.year + 1, 1, 1)
        else:
            next_month = date(current_month.year, current_month.month + 1, 1)
        
        # Get transactions for this month
        month_transactions = await get_month_transactions(db, user_id, current_month, next_month)
        
        # Calculate monthly expenses and savings
        monthly_expenses = sum(transaction.amount for transaction in month_transactions)
        actual_savings = monthly_income - monthly_expenses
        
        # Calculate deficit for this month
        monthly_deficit = max(0, monthly_savings_goal - actual_savings)
        
        # Update totals
        total_deficit += monthly_deficit
        total_saved += actual_savings
        
        # Move to next month
        current_month = next_month
    
    # Add current month's savings
    current_month_transactions = await get_month_transactions(
        db, 
        user_id, 
        date(today.year, today.month, 1), 
        today + timedelta(days=1)
    )
    current_month_expenses = sum(transaction.amount for transaction in current_month_transactions)
    
    # Proportional calculation for current month
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    proportional_income = (monthly_income / days_in_month) * days_elapsed
    current_month_savings = proportional_income - current_month_expenses
    
    # Add to total saved
    total_saved += current_month_savings
    
    # Calculate adjusted monthly goal if months remaining > 0
    adjusted_monthly_goal = monthly_savings_goal
    if months_remaining > 0:
        adjusted_monthly_goal = monthly_savings_goal + (total_deficit / months_remaining)
    
    # Calculate progress percentage
    progress_percentage = (total_saved / yearly_target) * 100 if yearly_target > 0 else 0
    
    # Calculate period end date (end of year)
    period_end_date = datetime(today.year, 12, 31, 23, 59, 59)
    
    # Calculate remaining amount
    remaining_amount = max(0, yearly_target - total_saved)
    
    return {
        "target_amount": yearly_target,
        "saved_amount": total_saved,
        "progress_percentage": progress_percentage,
        "period_end_date": period_end_date,
        "remaining_amount": remaining_amount,
        "adjusted_monthly_goal": adjusted_monthly_goal
    }

async def get_journey_start_date(db: AsyncSession, user_id: str) -> date:
    """Get the first transaction date for the user"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date)
        .limit(1)
    )
    
    first_transaction = result.scalar_one_or_none()
    if first_transaction and first_transaction.transaction_date:
        return first_transaction.transaction_date.date()
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

def determine_status(progress_percentage: float, period: str, today: date) -> str:
    """Determine the status based on progress percentage and time elapsed in period"""
    if progress_percentage >= 100:
        return "Goal Achieved"
    
    # Calculate time elapsed percentage based on period
    if period == "daily":
        # Time elapsed in the day
        elapsed_percentage = datetime.now().hour / 24 * 100
    elif period == "weekly":
        # Days elapsed in the week (0-6)
        elapsed_percentage = (today.weekday() + 1) / 7 * 100
    elif period == "monthly":
        # Days elapsed in the month
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        elapsed_percentage = today.day / days_in_month * 100
    else:  # yearly
        # Days elapsed in the year
        days_in_year = 366 if calendar.isleap(today.year) else 365
        elapsed_percentage = (today.timetuple().tm_yday / days_in_year) * 100
    
    # Determine status based on progress and time elapsed
    if progress_percentage >= 75:
        return "On Track"
    elif progress_percentage >= 50:
        return "In Progress"
    elif elapsed_percentage > 50:
        return "Behind Target"
    else:
        return "In Progress"