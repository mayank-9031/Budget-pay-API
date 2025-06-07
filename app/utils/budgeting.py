# app/utils/budgeting.py
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from app.models.category import Category
from app.models.expense import Expense, FrequencyType
from app.models.transaction import Transaction

def calculate_monthly_recurring_total(expenses: List[Expense], as_of: date = date.today()) -> float:
    """
    Sum up all recurring expenses that are currently active for this month.
    We assume that if next_due_date is within this month, we include it; 
    for daily/weekly, multiply appropriately.
    For simplicity, we assume:
      - daily: amount * (remaining days in month)
      - weekly: amount * (number of weeks in month, approx)
      - monthly: amount (once)
      - custom: prorate by interval_days within month
    """
    total = 0.0
    today = as_of
    year = today.year
    month = today.month
    # find last day of month
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    for exp in expenses:
        if not exp.is_active or exp.frequency_type == FrequencyType.one_time:
            continue
        if exp.frequency_type == FrequencyType.monthly:
            total += exp.amount
        elif exp.frequency_type == FrequencyType.weekly:
            # approximate 4.25 weeks in a month
            total += exp.amount * 4.25
        elif exp.frequency_type == FrequencyType.daily:
            days_remaining = (last_day - today).days + 1
            total += exp.amount * days_remaining
        elif exp.frequency_type == FrequencyType.custom and exp.interval_days:
            # count how many occurrences this month
            # naive: total days in month / interval_days * amount
            days_in_month = (last_day - date(year, month, 1)).days + 1
            occurrences = days_in_month // exp.interval_days
            total += exp.amount * occurrences
    return total

def allocate_budget(
    monthly_income: float,
    saving_goal_amount: Optional[float],
    categories: List[Category],
    expenses: List[Expense],
    transactions: List[Transaction],
) -> Dict[str, float]:
    """
    Core budget allocation function:
      1. Deduct recurring total from monthly_income → net_available.
      2. If saving_goal_amount is set:
          - set aside a portion each month towards that (e.g. fixed or %).
      3. Allocate net_available - saving to categories based on default/custom percentages.
      4. Return a dict { category_name: allocated_amount }.
    TODO: Replace 50/30/20 with ML-driven logic (placeholder).
    """
    # 1. Recurring total:
    from datetime import date
    monthly_recurring = calculate_monthly_recurring_total(expenses, as_of=date.today())
    # 2. If user has a savings goal, we might want to force a portion aside. 
    #    For MVP, assume savings goal is 20% if not overridden.
    target_savings = 0.2 * (monthly_income - monthly_recurring)
    # Override if user specified “savings_goal_amount”? For simplicity, use default 20%.
    net_after_fixed = monthly_income - monthly_recurring - target_savings

    # 3. Determine total percentage across categories (sum default/custom).
    #    If user provided custom_percentage, use that; else default_percentage.
    total_percent = 0.0
    allocation = {}
    for cat in categories:
        pct = cat.custom_percentage if (cat.custom_percentage is not None) else cat.default_percentage
        total_percent += pct

    if total_percent == 0:
        # fallback: equal distribution
        equal_share = net_after_fixed / len(categories)
        for cat in categories:
            allocation[cat.name] = equal_share
    else:
        for cat in categories:
            pct = cat.custom_percentage if (cat.custom_percentage is not None) else cat.default_percentage
            allocated_amt = (pct / total_percent) * net_after_fixed
            allocation[cat.name] = round(allocated_amt, 2)

    # 4. You could adjust based on actual spend so far this month (transactions),
    #    e.g., if underspending or overspending, dynamically adjust. Placeholder:
    #    for cat in categories: 
    #        spent = sum(tx.amount for tx in transactions if tx.category_id == cat.id)
    #        if spent > allocation[cat.name]:
    #            # overspend: reduce next month’s allocation proportionally, etc.
    return allocation

def calculate_daily_budget(monthly_income: float, expenses: List[Expense]) -> float:
    """
    Daily budget = (monthly_income - total_recurring_this_month) / (number_of_days_this_month).
    """
    from datetime import date
    today = date.today()
    # last day
    if today.month == 12:
        last_day = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(today.year, today.month + 1, 1) - timedelta(days=1)

    days_in_month = (last_day - date(today.year, today.month, 1)).days + 1
    recurring = calculate_monthly_recurring_total(expenses, as_of=today)
    remaining = monthly_income - recurring
    if days_in_month <= 0:
        return 0.0
    return round(remaining / days_in_month, 2)

def rebalance_if_overspent(
    category_name: str,
    overspend_amount: float,
    allocation: Dict[str, float],
    categories: List[Category],
) -> Dict[str, float]:
    """
    If user overspends in one category, re-allocate the remaining budgets across other categories.
    Placeholder logic: subtract overspend from other categories proportionally.
    """
    if category_name not in allocation or overspend_amount <= 0:
        return allocation

    # Remove overspent amount from that category’s allocation
    allocation[category_name] = max(0.0, allocation[category_name] - overspend_amount)
    remaining_cats = [c for c in allocation if c != category_name]
    if not remaining_cats:
        return allocation

    # Distribute overspend_amount across others based on current allocation proportion
    sum_rest = sum(allocation[c] for c in remaining_cats)
    if sum_rest <= 0:
        return allocation

    for c in remaining_cats:
        proportion = allocation[c] / sum_rest
        allocation[c] = round(allocation[c] - (overspend_amount * proportion), 2)
        if allocation[c] < 0:
            allocation[c] = 0.0
    return allocation
