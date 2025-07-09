from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import json
import httpx
import os
from collections import defaultdict
import uuid
import asyncio

from app.api.deps import get_current_user
from app.core.auth import User
from app.schemas.chatbot import ChatbotRequest, ChatbotResponse
from app.core.config import settings
from app.core.database import get_async_session
from app.crud.transaction import get_transactions_for_user
from app.crud.category import get_categories_for_user
from datetime import datetime, timedelta
import calendar

router = APIRouter()

# Model ID for OpenRouter - using a valid model that works
# OPENROUTER_MODEL_ID = "meta-llama/llama-3.2-3b-instruct"
OPENROUTER_MODEL_ID = "deepseek/deepseek-chat-v3-0324:free"

@router.post("/ask", response_model=ChatbotResponse)
async def ask_chatbot(
    request: Request,
    chatbot_request: ChatbotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ask a question to the AI chatbot.
    
    The chatbot can answer:
    - General finance and budgeting questions
    - Specific questions about the user's financial data
    """
    try:
        # Fetch user data from the database
        user_data = await prepare_user_data(current_user, db)
        
        # Create system prompt
        system_prompt = """
        You are a helpful financial assistant for a budget management application called Budget Pay. 
        You have access to the user's financial data including transactions, income, savings goals, and budget categories.
        
        You can answer two types of questions:
        1. General finance and budgeting questions
        2. Specific questions about the user's financial data
        
        For specific questions, use the provided user data to calculate accurate answers.
        Always be helpful, concise, and provide actionable advice when appropriate.
        
        When analyzing spending patterns or making recommendations:
        - Consider the user's income and savings goals
        - Look at category-specific spending
        - Identify trends in daily/weekly/monthly spending
        - Suggest practical ways to improve financial habits
        
        IMPORTANT: When asked about specific spending in categories or time periods:
        - Use the detailed spending data provided in the "category_spending_by_period" section
        - If asked about spending in a specific category for a specific time period (e.g., "How much did I spend on shopping this month?"), 
          look up the category name in the monthly_spending or current_month_by_category data
        - Perform calculations as needed to answer specific questions about spending patterns
        - If the data doesn't contain the exact information requested, use the available data to make the closest approximation
        
        IMPORTANT: When asked about savings goals or budget progress:
        - Calculate based on the user's monthly income and spending patterns
        - Use the user's savings_goal_amount to determine progress
        - Consider the difference between income and expenses to determine if the user is on track
        
        IMPORTANT: All monetary values should be treated as USD. Format currency as $X.XX.
        Never make up information. If you don't have enough data to answer a question accurately, say so.
        """
        
        # Create user prompt with data
        user_data_str = json.dumps(user_data)
        user_prompt = f"""
        User query: {chatbot_request.query}
        
        User financial data: {user_data_str}
        
        Please provide a helpful response based on this information.
        If the user is asking about specific spending in a category or time period, use the detailed spending data in the "category_spending_by_period" section to calculate the exact answer.
        If the user is asking about savings goals or budget progress, calculate based on their income, spending patterns, and savings goal amount.
        """
        
        # Use OpenRouter API with a valid Llama model
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.BACKEND_BASE_URL,  # Required for OpenRouter API
            "X-Title": "Budget Pay Financial Assistant"  # Optional but recommended
        }
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "model": OPENROUTER_MODEL_ID,  # Use the defined model ID
            "temperature": 0.1,
            "max_tokens": 1024
        }
        
        # Use httpx for async HTTP requests with proper error handling
        client = httpx.AsyncClient(timeout=60.0)
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error from OpenRouter API: {response.text}"
                )
            
            # Extract response content
            response_data = response.json()
            ai_response = response_data["choices"][0]["message"]["content"]
            
            return {"response": ai_response}
        finally:
            await client.aclose()
        
        # # GROQ Implementation (commented out for future use)
        # # Generate response using Groq API via direct HTTP request
        # headers = {
        #     "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        #     "Content-Type": "application/json"
        # }
        # 
        # payload = {
        #     "messages": [
        #         {"role": "system", "content": system_prompt},
        #         {"role": "user", "content": user_prompt}
        #     ],
        #     "model": "llama-3.1-8b-instant",
        #     "temperature": 0.1,
        #     "max_tokens": 1024
        # }
        # 
        # # Use httpx for async HTTP requests
        # client = httpx.AsyncClient(timeout=30.0)
        # try:
        #     response = await client.post(
        #         "https://api.groq.com/openai/v1/chat/completions",
        #         headers=headers,
        #         json=payload
        #     )
        #     
        #     if response.status_code != 200:
        #         raise HTTPException(
        #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        #             detail=f"Error from Groq API: {response.text}"
        #         )
        #     
        #     # Extract response content
        #     response_data = response.json()
        #     ai_response = response_data["choices"][0]["message"]["content"]
        #     
        #     return {"response": ai_response}
        # finally:
        #     await client.aclose()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating chatbot response: {str(e)}"
        )

async def prepare_user_data(user: User, db: AsyncSession) -> dict:
    """Prepare user data in a structured format for the AI model."""
    # Get current date information
    today = datetime.now()
    start_of_month = datetime(today.year, today.month, 1)
    end_of_month = datetime(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    start_of_week = (today - timedelta(days=today.weekday()))
    end_of_week = (start_of_week + timedelta(days=6))
    
    # Previous month
    if today.month == 1:
        prev_month_start = datetime(today.year - 1, 12, 1)
        prev_month_end = datetime(today.year - 1, 12, 31)
    else:
        prev_month_start = datetime(today.year, today.month - 1, 1)
        prev_month_end = datetime(today.year, today.month - 1, calendar.monthrange(today.year, today.month - 1)[1])
    
    # Helper function for safe float conversion
    def safe_float(value, default=0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    # Basic user info
    user_info = {
        "id": str(user.id),
        "email": user.email,
        "full_name": getattr(user, "full_name", "") or "",
        "monthly_income": safe_float(getattr(user, "monthly_income", 0)),
        "savings_goal_amount": safe_float(getattr(user, "savings_goal_amount", 0))
    }
    
    # Fetch transactions from the database
    # Convert SQLAlchemy Column[UUID] to Python UUID
    user_id = uuid.UUID(str(user.id))
    db_transactions = await get_transactions_for_user(user_id, db)
    
    # Process transactions
    transactions = []
    monthly_spending = 0
    weekly_spending = 0
    daily_spending = {}
    category_spending = defaultdict(float)
    total_income = 0
    total_expenses = 0
    
    # Track spending by category and time period
    category_spending_by_period = {
        "current_month": defaultdict(float),
        "current_week": defaultdict(float),
        "previous_month": defaultdict(float),
        "last_7_days": defaultdict(float),
        "by_day": {},
        "by_month": {}
    }
    
    # Create a map of category IDs to names for easier reference
    category_id_to_name = {}
    
    # Fetch categories from the database
    db_categories = await get_categories_for_user(user_id, db)
    
    # Process categories
    categories = []
    for cat in db_categories:
        # Use custom_percentage if available, otherwise default_percentage
        budget_percentage = safe_float(cat.custom_percentage) if hasattr(cat, 'custom_percentage') and cat.custom_percentage is not None else safe_float(cat.default_percentage)
        
        cat_dict = {
            "id": str(cat.id),
            "name": cat.name,
            "budget_percentage": budget_percentage,
            "description": cat.description if hasattr(cat, 'description') else "",
            "color": getattr(cat, "color", "#CCCCCC"),
            "spending": 0,  # Will be updated after processing transactions
            "budget_amount": user_info["monthly_income"] * (budget_percentage / 100) if budget_percentage > 0 else 0
        }
        categories.append(cat_dict)
        
        # Add to the category ID to name map
        category_id_to_name[str(cat.id)] = cat.name
    
    # Process transactions
    for tx in db_transactions:
        # Skip transactions without dates
        if tx.transaction_date is None:
            continue
            
        tx_date = tx.transaction_date
        tx_amount = safe_float(tx.amount)
        
        # Determine if it's an expense or income based on amount
        # Negative amounts are expenses, positive are income
        tx_type = "expense" if tx_amount < 0 else "income"
        
        # Use absolute value for display
        display_amount = abs(tx_amount)
        
        # Track total income and expenses
        if tx_type == "income":
            total_income += display_amount
        else:
            total_expenses += display_amount
        
        # Get category name
        category_id = str(tx.category_id) if tx.category_id is not None else None
        category_name = category_id_to_name.get(category_id, "Uncategorized") if category_id else "Uncategorized"
        
        # Add to transactions list
        tx_dict = {
            "id": str(tx.id),
            "amount": display_amount,
            "description": tx.description,
            "date": tx.transaction_date.isoformat(),
            "category_id": category_id,
            "category_name": category_name,
            "type": tx_type
        }
        transactions.append(tx_dict)
        
        # Only track expenses for spending metrics
        if tx_type == "expense":
            # Track category spending
            if category_id:
                category_spending[category_id] += display_amount
            
            # Monthly spending
            if start_of_month.date() <= tx_date.date() <= end_of_month.date():
                monthly_spending += display_amount
                
                # Track by category for current month
                if category_id:
                    category_spending_by_period["current_month"][category_id] += display_amount
            
            # Previous month spending
            if prev_month_start.date() <= tx_date.date() <= prev_month_end.date():
                if category_id:
                    category_spending_by_period["previous_month"][category_id] += display_amount
            
            # Weekly spending
            if start_of_week.date() <= tx_date.date() <= end_of_week.date():
                weekly_spending += display_amount
                
                # Track by category for current week
                if category_id:
                    category_spending_by_period["current_week"][category_id] += display_amount
            
            # Daily spending (last 7 days)
            for i in range(7):
                day = (today - timedelta(days=i))
                day_start = datetime(day.year, day.month, day.day)
                day_end = datetime(day.year, day.month, day.day, 23, 59, 59)
                
                if day_start.date() <= tx_date.date() <= day_end.date():
                    day_str = day_start.date().isoformat()
                    
                    # Track total spending for this day
                    if day_str not in daily_spending:
                        daily_spending[day_str] = 0
                    daily_spending[day_str] += display_amount
                    
                    # Track spending by category for this day
                    if day_str not in category_spending_by_period["by_day"]:
                        category_spending_by_period["by_day"][day_str] = defaultdict(float)
                    
                    if category_id:
                        category_spending_by_period["by_day"][day_str][category_id] += display_amount
                    
                    # Also track in last_7_days
                    if category_id:
                        category_spending_by_period["last_7_days"][category_id] += display_amount
            
            # Track spending by month
            month_key = f"{tx_date.year}-{tx_date.month:02d}"
            if month_key not in category_spending_by_period["by_month"]:
                category_spending_by_period["by_month"][month_key] = defaultdict(float)
            
            if category_id:
                category_spending_by_period["by_month"][month_key][category_id] += display_amount
    
    # Update category spending totals and calculate budget status
    for cat in categories:
        cat["spending"] = category_spending.get(cat["id"], 0)
        cat["remaining_budget"] = cat["budget_amount"] - cat["spending"]
        cat["budget_status"] = "under_budget" if cat["remaining_budget"] >= 0 else "over_budget"
        cat["percentage_used"] = (cat["spending"] / cat["budget_amount"] * 100) if cat["budget_amount"] > 0 else 0
    
    # Convert defaultdicts to regular dicts for JSON serialization
    category_spending_by_period_json = {}
    for period, data in category_spending_by_period.items():
        if isinstance(data, defaultdict):
            category_spending_by_period_json[period] = dict(data)
        elif isinstance(data, dict):
            period_dict = {}
            for day, day_data in data.items():
                if isinstance(day_data, defaultdict):
                    period_dict[day] = dict(day_data)
                else:
                    period_dict[day] = day_data
            category_spending_by_period_json[period] = period_dict
    
    # Add category names to the spending data for easier reference
    category_spending_with_names = {}
    for category_id, amount in category_spending.items():
        category_name = category_id_to_name.get(category_id, "Uncategorized")
        category_spending_with_names[category_name] = amount
    
    # Calculate derived metrics
    monthly_income = user_info["monthly_income"]
    remaining_monthly_budget = monthly_income - monthly_spending
    remaining_weekly_budget = (monthly_income / 4) - weekly_spending
    
    # Calculate savings metrics based on transactions
    current_month_savings = monthly_income - monthly_spending if monthly_income > monthly_spending else 0
    savings_goal_amount = user_info["savings_goal_amount"]
    savings_goal_progress = (current_month_savings / savings_goal_amount * 100) if savings_goal_amount > 0 else 0
    
    # Calculate average daily spending
    days_in_data = len(daily_spending) if daily_spending else 1
    average_daily_spending = sum(daily_spending.values()) / days_in_data if days_in_data > 0 else 0
    
    # Find biggest expense category
    biggest_category = {"id": None, "name": "Unknown", "amount": 0}
    for cat in categories:
        if cat["spending"] > biggest_category["amount"]:
            biggest_category = {
                "id": cat["id"],
                "name": cat["name"],
                "amount": cat["spending"]
            }
    
    # Add current month name for reference
    current_month_name = today.strftime("%B %Y")
    previous_month_name = prev_month_start.strftime("%B %Y")
    
    # Calculate budget allocation and spending breakdown
    budget_allocation = {}
    for cat in categories:
        if cat["budget_percentage"] > 0:
            budget_allocation[cat["name"]] = cat["budget_percentage"]
    
    # Calculate spending trends (week-over-week)
    # Get last week's data
    last_week_start = start_of_week - timedelta(days=7)
    last_week_end = end_of_week - timedelta(days=7)
    last_week_spending = 0
    
    for tx in db_transactions:
        if tx.transaction_date is None:
            continue
            
        tx_date = tx.transaction_date
        tx_amount = safe_float(tx.amount)
        
        if tx_amount < 0 and last_week_start.date() <= tx_date.date() <= last_week_end.date():
            last_week_spending += abs(tx_amount)
    
    spending_trend = {
        "this_week": weekly_spending,
        "last_week": last_week_spending,
        "change_percentage": ((weekly_spending - last_week_spending) / last_week_spending * 100) if last_week_spending > 0 else 0,
        "trend": "increasing" if weekly_spending > last_week_spending else "decreasing" if weekly_spending < last_week_spending else "stable"
    }
    
    # Compile final data structure
    return {
        "user": user_info,
        "transactions": transactions,
        "categories": categories,
        "derived_data": {
            "today": today.date().isoformat(),
            "current_month": current_month_name,
            "previous_month": previous_month_name,
            "start_of_month": start_of_month.date().isoformat(),
            "end_of_month": end_of_month.date().isoformat(),
            "start_of_week": start_of_week.date().isoformat(),
            "end_of_week": end_of_week.date().isoformat(),
            "monthly_spending": monthly_spending,
            "weekly_spending": weekly_spending,
            "daily_spending": daily_spending,
            "average_daily_spending": average_daily_spending,
            "remaining_monthly_budget": remaining_monthly_budget,
            "remaining_weekly_budget": remaining_weekly_budget,
            "savings_goal_amount": savings_goal_amount,
            "current_month_savings": current_month_savings,
            "savings_goal_progress": savings_goal_progress,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "biggest_expense_category": biggest_category,
            "category_spending": category_spending_with_names,
            "category_spending_by_period": category_spending_by_period_json,
            "budget_allocation": budget_allocation,
            "spending_trend": spending_trend
        }
    } 