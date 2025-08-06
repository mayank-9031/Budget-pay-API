# app/utils/budgeting.py
import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.core.auth import User


# ────────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY
# ────────────────────────────────────────────────────────────────────────────────
async def calculate_goal_progress(
    user: User,
    period: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Return savings-goal progress for the requested period
    (daily, weekly, monthly, yearly), using *full* income figures
    and day-accurate scaling.
    """
    if not user.monthly_income or not user.savings_goal_amount:
        # Nothing set → short-circuit
        return _empty_result()

    monthly_income = float(user.monthly_income)
    monthly_goal   = float(user.savings_goal_amount)

    today         = datetime.now().date()
    journey_start = await get_journey_start_date(db, user.id) or today

    # Pull transactions for the active period
    transactions   = await get_period_transactions(db, user.id, period,
                                                   today, journey_start)
    period_expenses = sum(t.amount for t in transactions)

    # Route to period-specific calculator
    if period == "daily":
        result = _daily_progress(monthly_income, monthly_goal,
                                 period_expenses, today, journey_start)
    elif period == "weekly":
        result = _weekly_progress(monthly_income, monthly_goal,
                                  period_expenses, today, journey_start)
    elif period == "yearly":
        result = await _yearly_progress(monthly_income, monthly_goal,
                                        user.id, db, today, journey_start)
    else:  # default → monthly
        result = _monthly_progress(monthly_income, monthly_goal,
                                   period_expenses, today, journey_start)

    # Post-processing
    result["status"]              = determine_status(result["progress_percentage"],
                                                     period, today, journey_start)
    
    # FIX: Handle division by zero for percentage_of_income
    result["percentage_of_income"] = (monthly_goal / monthly_income * 100) if monthly_income > 0 else 0.0
    
    result["journey_start_date"]   = journey_start
    result["days_in_journey"]      = (today - journey_start).days + 1

    return result


# ────────────────────────────────────────────────────────────────────────────────
# HELPERS – COMMON
# ────────────────────────────────────────────────────────────────────────────────
def _empty_result() -> Dict[str, Any]:
    return {
        "target_amount":        0.0,
        "saved_amount":         0.0,
        "progress_percentage":  0.0,
        "status":               "Not Set",
        "period_end_date":      datetime.now(),
        "percentage_of_income": 0.0,
        "remaining_amount":     0.0,
        "journey_start_date":   None,
        "days_in_journey":      0,
        "budget_till_now":      0.0
    }


def _days_in_month(day: date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


# ────────────────────────────────────────────────────────────────────────────────
# DAILY
# ────────────────────────────────────────────────────────────────────────────────
def _daily_progress(monthly_income: float, monthly_goal: float,
                    daily_expenses: float, today: date, journey_start: date
                    ) -> Dict[str, Any]:

    if journey_start > today:
        return _empty_result()

    dim          = _days_in_month(today)
    daily_income = monthly_income / dim
    daily_target = monthly_goal   / dim

    budget_till_now = daily_income                      # full day
    saved_amount    = budget_till_now - daily_expenses
    progress_pct    = (saved_amount / daily_target) * 100 if daily_target else 0
    remaining_amt   = max(0, daily_target - saved_amount)

    return {
        "target_amount":       daily_target,
        "saved_amount":        saved_amount,
        "progress_percentage": progress_pct,
        "period_end_date":     datetime.combine(today, datetime.max.time()),
        "remaining_amount":    remaining_amt,
        "budget_till_now":     budget_till_now
    }


# ────────────────────────────────────────────────────────────────────────────────
# WEEKLY
# ────────────────────────────────────────────────────────────────────────────────
def _weekly_progress(monthly_income: float, monthly_goal: float,
                     weekly_expenses: float, today: date, journey_start: date
                     ) -> Dict[str, Any]:

    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end   = week_start + timedelta(days=6)           # Sunday
    effective_start = max(week_start, journey_start)

    if effective_start > today:
        return _empty_result()

    dim           = _days_in_month(today)
    daily_income  = monthly_income / dim
    daily_target  = monthly_goal   / dim

    days_elapsed       = (today - effective_start).days + 1
    # CHANGED: Use remaining days from journey start to week end
    days_from_start_to_end = (week_end - effective_start).days + 1
    
    budget_till_now    = daily_income  * days_elapsed
    target_amount      = daily_target * days_from_start_to_end  # CHANGED
    saved_amount       = budget_till_now - weekly_expenses
    progress_pct       = (saved_amount / target_amount) * 100 if target_amount else 0
    remaining_amt      = max(0, target_amount - saved_amount)

    return {
        "target_amount":       target_amount,
        "saved_amount":        saved_amount,
        "progress_percentage": progress_pct,
        "period_end_date":     datetime.combine(week_end, datetime.max.time()),
        "remaining_amount":    remaining_amt,
        "budget_till_now":     budget_till_now
    }


# ────────────────────────────────────────────────────────────────────────────────
# MONTHLY
# ────────────────────────────────────────────────────────────────────────────────
def _monthly_progress(monthly_income: float, monthly_goal: float,
                      monthly_expenses: float, today: date, journey_start: date
                      ) -> Dict[str, Any]:

    month_start     = date(today.year, today.month, 1)
    last_dom        = _days_in_month(today)
    month_end       = date(today.year, today.month, last_dom)
    effective_start = max(month_start, journey_start)

    if effective_start > today:
        return _empty_result()

    dim            = last_dom
    daily_income   = monthly_income / dim
    daily_target   = monthly_goal   / dim

    days_elapsed   = (today - effective_start).days + 1
    # CHANGED: Use remaining days from journey start to month end
    days_from_start_to_end = (month_end - effective_start).days + 1
    
    budget_till_now = daily_income  * days_elapsed
    target_amount   = daily_target * days_from_start_to_end  # CHANGED
    saved_amount    = budget_till_now - monthly_expenses
    progress_pct    = (saved_amount / target_amount) * 100 if target_amount else 0
    remaining_amt   = max(0, target_amount - saved_amount)

    return {
        "target_amount":       target_amount,
        "saved_amount":        saved_amount,
        "progress_percentage": progress_pct,
        "period_end_date":     datetime(today.year, today.month, last_dom, 23, 59, 59),
        "remaining_amount":    remaining_amt,
        "budget_till_now":     budget_till_now
    }


# ────────────────────────────────────────────────────────────────────────────────
# YEARLY
# ────────────────────────────────────────────────────────────────────────────────
async def _yearly_progress(monthly_income: float, monthly_goal: float,
                           user_id: str, db: AsyncSession,
                           today: date, journey_start: date
                           ) -> Dict[str, Any]:

    year_start      = date(today.year, 1, 1)
    year_end        = date(today.year, 12, 31)
    effective_start = max(year_start, journey_start)

    if effective_start > today:
        return _empty_result()

    days_in_year     = 366 if calendar.isleap(today.year) else 365
    daily_income     = (monthly_income * 12) / days_in_year
    daily_target     = (monthly_goal   * 12) / days_in_year

    days_elapsed     = (today - effective_start).days + 1
    # CHANGED: Use remaining days from journey start to year end
    days_from_start_to_end = (year_end - effective_start).days + 1
    
    budget_till_now  = daily_income  * days_elapsed
    target_amount    = daily_target * days_from_start_to_end  # CHANGED

    # expenses since journey_start (within this year)
    transactions = await get_period_transactions(db, user_id, "yearly",
                                                 today, journey_start)
    total_expenses = sum(t.amount for t in transactions)

    saved_amount   = budget_till_now - total_expenses
    progress_pct   = (saved_amount / target_amount) * 100 if target_amount else 0
    remaining_amt  = max(0, target_amount - saved_amount)

    # Optional helper for users: how much should I now save monthly?
    remaining_days = (year_end - today).days
    remaining_months = remaining_days / 30.44 if remaining_days > 0 else 0
    adjusted_monthly_goal = (remaining_amt / remaining_months) if remaining_months else monthly_goal

    return {
        "target_amount":        target_amount,
        "saved_amount":         saved_amount,
        "progress_percentage":  progress_pct,
        "period_end_date":      datetime(today.year, 12, 31, 23, 59, 59),
        "remaining_amount":     remaining_amt,
        "adjusted_monthly_goal": adjusted_monthly_goal,
        "budget_till_now":      budget_till_now
    }


# ────────────────────────────────────────────────────────────────────────────────
# DATABASE HELPERS
# ────────────────────────────────────────────────────────────────────────────────
async def get_period_transactions(
    db: AsyncSession,
    user_id: str,
    period: str,
    today: date,
    journey_start: date
) -> List[Transaction]:
    """Return transactions inside the current period, clipped by journey start."""
    if period == "daily":
        period_start = today if journey_start <= today else None
    elif period == "weekly":
        week_start   = today - timedelta(days=today.weekday())
        period_start = max(week_start, journey_start)
    elif period == "monthly":
        month_start  = date(today.year, today.month, 1)
        period_start = max(month_start, journey_start)
    elif period == "yearly":
        year_start   = date(today.year, 1, 1)
        period_start = max(year_start, journey_start)
    else:
        period_start = None

    if not period_start:
        return []

    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt   = datetime.combine(today, datetime.max.time())

    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= start_dt,
            Transaction.transaction_date <= end_dt
        )
    )
    return result.scalars().all()


async def get_journey_start_date(db: AsyncSession, user_id: str) -> Optional[date]:
    """First transaction date for the user (or None)."""
    result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
                           .order_by(Transaction.transaction_date)
                           .limit(1)
    )
    first_tx = result.scalar_one_or_none()
    return first_tx.transaction_date.date() if first_tx else None


# ────────────────────────────────────────────────────────────────────────────────
# MISC
# ────────────────────────────────────────────────────────────────────────────────
def determine_status(progress_percentage: float, period: str,
                     today: date, journey_start: date) -> str:
    """Status text driven by progress vs time elapsed."""
    if progress_percentage >= 100:
        return "Goal Achieved"

    # elapsed %
    if period == "daily":
        elapsed_pct = (datetime.now().hour / 24) * 100 if journey_start == today else 100
    elif period == "weekly":
        week_start = today - timedelta(days=today.weekday())
        days_elapsed = (today - max(week_start, journey_start)).days + 1
        elapsed_pct  = min(days_elapsed / 7 * 100, 100)
    elif period == "monthly":
        month_start  = date(today.year, today.month, 1)
        days_elapsed = (today - max(month_start, journey_start)).days + 1
        dim          = _days_in_month(today)
        elapsed_pct  = min(days_elapsed / dim * 100, 100)
    else:  # yearly
        year_start   = date(today.year, 1, 1)
        days_elapsed = (today - max(year_start, journey_start)).days + 1
        diy          = 366 if calendar.isleap(today.year) else 365
        elapsed_pct  = min(days_elapsed / diy * 100, 100)

    if progress_percentage >= 75:
        return "On Track"
    if progress_percentage >= 50:
        return "In Progress"
    if elapsed_pct > 50 and progress_percentage < 25:
        return "Behind Target"
    return "In Progress"
