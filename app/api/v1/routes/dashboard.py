# app/api/v1/routes/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict
from datetime import date, datetime, timedelta
from app.core.database import get_async_session
from app.core.auth import current_active_user, User
from app.crud.category import get_categories_for_user
from app.crud.expense import get_expenses_for_user
from app.crud.transaction import get_transactions_for_user
from app.utils.budgeting import allocate_budget, calculate_daily_budget, calculate_monthly_recurring_total

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/summary")
async def get_dashboard_summary(
    period: Optional[str] = Query("month", description="day | week | month | year"),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> Dict:
    """
    Returns a summary dict for the requested period:
      - total_income (monthly_income)
      - total_recurring_expenses
      - total_spent (from transactions in period)
      - allocation_per_category (dict)
      - daily_budget (float)
      - category_health: {category_name: {allocated, spent, diff}}
    """
    # 1. Fetch user’s monthly income
    try:
        monthly_income = float(user.monthly_income) if user.monthly_income else 0.0
    except:
        monthly_income = 0.0

    # 2. Fetch all active recurring expenses
    expenses = await get_expenses_for_user(user.id, db)
    recurring_total = calculate_monthly_recurring_total(expenses, as_of=date.today())

    # 3. Fetch all categories
    categories = await get_categories_for_user(user.id, db)

    # 4. Fetch all transactions for user
    transactions = await get_transactions_for_user(user.id, db)
    # Filter transactions based on `period`
    # For simplicity, if period=="month", get all transactions with transaction_date in current month
    filtered_tx = []
    now = datetime.utcnow()
    if period == "month":
        filtered_tx = [
            tx for tx in transactions
            if tx.transaction_date.month == now.month and tx.transaction_date.year == now.year
        ]
    elif period == "week":
        # last 7 days
        cutoff = now - timedelta(days=7)
        filtered_tx = [tx for tx in transactions if tx.transaction_date >= cutoff]
    elif period == "day":
        filtered_tx = [tx for tx in transactions if tx.transaction_date.date() == now.date()]
    elif period == "year":
        filtered_tx = [tx for tx in transactions if tx.transaction_date.year == now.year]
    else:
        filtered_tx = transactions

    # 5. Compute allocation per category
    allocation = allocate_budget(monthly_income, None, categories, expenses, filtered_tx)

    # 6. Compute spent per category
    spent_per_cat = {}
    for cat in categories:
        spent_per_cat[cat.name] = sum(tx.amount for tx in filtered_tx if tx.category_id == cat.id)

    # 7. Category health: allocated vs spent
    category_health = {}
    for cat in categories:
        alloc_amt = allocation.get(cat.name, 0.0)
        spent_amt = spent_per_cat.get(cat.name, 0.0)
        category_health[cat.name] = {
            "allocated": alloc_amt,
            "spent": spent_amt,
            "remaining": round(alloc_amt - spent_amt, 2),
            "status": "green" if spent_amt <= alloc_amt else "red",
        }

    # 8. Daily budget
    daily_budget = calculate_daily_budget(monthly_income, expenses)

    return {
        "monthly_income": monthly_income,
        "recurring_total": recurring_total,
        "total_spent": sum(tx.amount for tx in filtered_tx),
        "allocation_per_category": allocation,
        "daily_budget": daily_budget,
        "category_health": category_health,
    }
