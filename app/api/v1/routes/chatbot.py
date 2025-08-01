from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import json
import httpx
import os
import logging

logger = logging.getLogger(__name__)
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
from app.utils.budgeting import calculate_goal_progress
from datetime import datetime, timedelta
import calendar

router = APIRouter()

# Model IDs for OpenRouter
PRIMARY_MODEL = "meta-llama/llama-3.2-3b-instruct"
FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324:free"

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
        - Use the detailed expense overview data available in the "expense_overview" section
        - This data contains category-wise spending details with allocated budget, actual spent, remaining amount, and progress percentage
        - It also includes status indicators (On Track, Near Limit, Over Budget) for each category
        
        IMPORTANT: When asked about savings goals or budget progress:
        - Use the "goal_progress" data which contains detailed information about the user's savings goal progress
        - This includes target amount, saved amount, progress percentage, status, period end date, and remaining amount
        - Goal status can be: Goal Achieved, On Track, In Progress, or Behind Target
        - Different time periods (daily, weekly, monthly, yearly) affect the calculations
        
        IMPORTANT: When asked about overall financial health or dashboard information:
        - Use the "dashboard_summary" data which provides comprehensive information
        - This includes income, spent, remaining budget, savings progress, spending trends, category allocation
        - It also includes daily spending patterns, top spending categories, and quick stats
        
        IMPORTANT: All monetary values should be treated as in local currency (₹). Format currency as ₹X,XX.
        Never make up information. If you don't have enough data to answer a question accurately, say so.
        
        User can view their financial data by different time periods: daily, weekly, monthly, and yearly.
        For percentage values, provide them rounded to two decimal places.
        """
        
        # Create user prompt with data
        user_data_str = json.dumps(user_data)
        user_prompt = f"""
        User query: {chatbot_request.query}
        
        User financial data: {user_data_str}
        
        Please provide a helpful response based on this information.
        If the user is asking about specific spending in a category or time period, use the expense overview data.
        If the user is asking about savings goals or budget progress, use the goal progress data.
        For overall financial insights, use the dashboard summary data.
        Give specific, data-backed answers to the user's questions and provide actionable advice when appropriate.
        Always format currency values using the ₹ symbol (e.g., ₹5,000).
        """
        
        # Use OpenRouter API with fallback model support
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.BACKEND_BASE_URL,  # Required for OpenRouter API
            "X-Title": "Budget Pay Financial Assistant"  # Optional but recommended
        }
        
        async def try_generate_response(model: str) -> dict:
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "model": model,
                "temperature": 0.1,
                "max_tokens": 1024
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    return {"success": True, "response": response_data["choices"][0]["message"]["content"]}
                return {"success": False, "error": response.text}

        # Try primary model first
        result = await try_generate_response(PRIMARY_MODEL)
        
        # If primary model fails, try fallback model
        if not result["success"]:
            logger.warning(f"Primary model failed: {result['error']}. Trying fallback model...")
            result = await try_generate_response(FALLBACK_MODEL)
            
            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Both models failed. Last error: {result['error']}"
                )
        
        return {"response": result["response"]}
        
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
    for tx in db_transactions:
        # Skip transactions without dates
        if tx.transaction_date is None:
            continue
            
        tx_date = tx.transaction_date
        tx_amount = safe_float(tx.amount)
        
        # Get category name
        category_name = tx.category.name if tx.category else "Uncategorized"
        
        # Add to transactions list
        tx_dict = {
            "id": str(tx.id),
            "amount": tx_amount,
            "description": tx.description,
            "date": tx.transaction_date.isoformat(),
            "category_id": str(tx.category_id) if tx.category_id else None,
            "category_name": category_name
        }
        transactions.append(tx_dict)
    
    # Get goal progress data for different periods
    daily_goal_progress = await calculate_goal_progress(user, "daily", db)
    weekly_goal_progress = await calculate_goal_progress(user, "weekly", db)
    monthly_goal_progress = await calculate_goal_progress(user, "monthly", db)
    yearly_goal_progress = await calculate_goal_progress(user, "yearly", db)
    
    # Structure goal progress data for all periods
    goal_progress = {
        "daily": {
            "target_amount": daily_goal_progress["target_amount"],
            "saved_amount": daily_goal_progress["saved_amount"],
            "progress_percentage": daily_goal_progress["progress_percentage"],
            "status": daily_goal_progress["status"],
            "period_end_date": daily_goal_progress["period_end_date"].isoformat() if isinstance(daily_goal_progress["period_end_date"], datetime) else daily_goal_progress["period_end_date"],
            "percentage_of_income": daily_goal_progress["percentage_of_income"],
            "remaining_amount": daily_goal_progress["remaining_amount"]
        },
        "weekly": {
            "target_amount": weekly_goal_progress["target_amount"],
            "saved_amount": weekly_goal_progress["saved_amount"],
            "progress_percentage": weekly_goal_progress["progress_percentage"],
            "status": weekly_goal_progress["status"],
            "period_end_date": weekly_goal_progress["period_end_date"].isoformat() if isinstance(weekly_goal_progress["period_end_date"], datetime) else weekly_goal_progress["period_end_date"],
            "percentage_of_income": weekly_goal_progress["percentage_of_income"],
            "remaining_amount": weekly_goal_progress["remaining_amount"]
        },
        "monthly": {
            "target_amount": monthly_goal_progress["target_amount"],
            "saved_amount": monthly_goal_progress["saved_amount"],
            "progress_percentage": monthly_goal_progress["progress_percentage"],
            "status": monthly_goal_progress["status"],
            "period_end_date": monthly_goal_progress["period_end_date"].isoformat() if isinstance(monthly_goal_progress["period_end_date"], datetime) else monthly_goal_progress["period_end_date"],
            "percentage_of_income": monthly_goal_progress["percentage_of_income"],
            "remaining_amount": monthly_goal_progress["remaining_amount"]
        },
        "yearly": {
            "target_amount": yearly_goal_progress["target_amount"],
            "saved_amount": yearly_goal_progress["saved_amount"],
            "progress_percentage": yearly_goal_progress["progress_percentage"],
            "status": yearly_goal_progress["status"],
            "period_end_date": yearly_goal_progress["period_end_date"].isoformat() if isinstance(yearly_goal_progress["period_end_date"], datetime) else yearly_goal_progress["period_end_date"],
            "percentage_of_income": yearly_goal_progress["percentage_of_income"],
            "remaining_amount": yearly_goal_progress["remaining_amount"],
            "adjusted_monthly_goal": yearly_goal_progress.get("adjusted_monthly_goal", user_info["savings_goal_amount"])
        }
    }
    
    # Get expense overview data (simulated since we're not making actual API calls within the backend)
    # This will mimic the structure of the expenses/overview/budget endpoint
    expense_overview = {
        "summary": {
            "time_period": "monthly",
            "period_label": "Monthly",
            "allocated": user_info["monthly_income"],
            "spent": sum(tx["amount"] for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}")),
            "remaining": user_info["monthly_income"] - sum(tx["amount"] for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}"))
        },
        "categories": []
    }
    
    # Get categories from the database
    db_categories = await get_categories_for_user(user_id, db)
    
    # Process categories and calculate spending for expense overview
    for cat in db_categories:
        # Calculate spending for this category in the current month
        category_spending = sum(tx["amount"] for tx in transactions 
                            if tx["category_id"] == str(cat.id) and 
                            tx["date"].startswith(f"{today.year}-{today.month:02d}"))
        
        # Calculate allocated budget for this category
        budget_percentage = safe_float(cat.custom_percentage) if hasattr(cat, 'custom_percentage') and cat.custom_percentage is not None else safe_float(cat.default_percentage)
        allocated = user_info["monthly_income"] * (budget_percentage / 100) if budget_percentage > 0 else 0
        
        # Calculate remaining budget
        remaining = allocated - category_spending
        
        # Determine status
        status = "On Track"
        if remaining < 0:
            status = "Over Budget"
        elif remaining <= allocated * 0.1:  # Within 10% of budget
            status = "Near Limit"
        
        # Calculate progress percentage
        progress_percentage = min(100, (category_spending / allocated * 100)) if allocated > 0 else 0
        
        # Add category to expense overview
        expense_overview["categories"].append({
            "id": str(cat.id),
            "name": cat.name,
            "allocated": allocated,
            "spent": category_spending,
            "remaining": remaining,
            "status": status,
            "progress_percentage": progress_percentage
        })
    
    # Fetch dashboard summary data (simplified version since we're not calling actual API)
    # This will mimic the structure of the dashboard/summary endpoint
    dashboard_summary = {
        "cards": {
            "time_period": "monthly",
            "period_label": "Monthly",
            "income": user_info["monthly_income"],
            "spent": expense_overview["summary"]["spent"],
            "remaining": expense_overview["summary"]["remaining"],
            "savings_progress": {
                "percentage": goal_progress["monthly"]["progress_percentage"],
                "saved_amount": goal_progress["monthly"]["saved_amount"],
                "goal_amount": goal_progress["monthly"]["target_amount"],
                "status": goal_progress["monthly"]["status"],
                "period_end_date": goal_progress["monthly"]["period_end_date"],
                "percentage_of_income": goal_progress["monthly"]["percentage_of_income"],
                "remaining_amount": goal_progress["monthly"]["remaining_amount"]
            }
        },
        "spending_trends": generate_spending_trends(transactions, today),
        "category_allocation": generate_category_allocation(db_categories, user_info["monthly_income"]),
        "daily_spending": generate_daily_spending(transactions, today),
        "top_spending_categories": sorted(expense_overview["categories"], key=lambda x: x["spent"], reverse=True)[:5],
        "quick_stats": {
            "total_transactions": len([tx for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}")]),
            "avg_transaction_amount": calculate_avg_transaction(transactions, today),
            "categories_used": len(set(tx["category_id"] for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}") and tx["category_id"]))
        },
        "category_health": expense_overview["categories"]
    }
    
    # Compile final data structure
    return {
        "user": user_info,
        "transactions": transactions,
        "goal_progress": goal_progress,
        "expense_overview": expense_overview,
        "dashboard_summary": dashboard_summary,
        "derived_data": {
            "today": today.date().isoformat(),
            "current_month": today.strftime("%B %Y"),
            "previous_month": prev_month_start.strftime("%B %Y"),
            "start_of_month": start_of_month.date().isoformat(),
            "end_of_month": end_of_month.date().isoformat(),
            "start_of_week": start_of_week.date().isoformat(),
            "end_of_week": end_of_week.date().isoformat()
        }
    }

def generate_spending_trends(transactions, today):
    """Generate spending trends data for the dashboard"""
    weekly_spending = defaultdict(float)
    
    # Get current month transactions
    month_transactions = [tx for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}")]
    
    # Group by week
    for week_num in range(1, 5):
        # Approximate week start and end (simplistic approach)
        week_start_day = (week_num - 1) * 7 + 1
        week_end_day = week_num * 7
        
        for tx in month_transactions:
            tx_day = int(tx["date"].split("T")[0].split("-")[2])
            if week_start_day <= tx_day <= week_end_day:
                weekly_spending[f"Week {week_num}"] += tx["amount"]
    
    # Format for dashboard
    trends = []
    for week_num in range(1, 5):
        trends.append({
            "label": f"Week {week_num}",
            "amount": weekly_spending.get(f"Week {week_num}", 0)
        })
    
    return trends

def generate_category_allocation(categories, monthly_income):
    """Generate category allocation data for the dashboard"""
    allocation = []
    for cat in categories:
        # Calculate allocated budget for this category
        budget_percentage = cat.custom_percentage if hasattr(cat, 'custom_percentage') and cat.custom_percentage is not None else cat.default_percentage
        allocated = monthly_income * (budget_percentage / 100) if budget_percentage > 0 else 0
        
        # Generate a color based on the category name
        color = f"#{hash(cat.name) % 0xffffff:06x}"
        
        allocation.append({
            "name": cat.name,
            "allocated": allocated,
            "color": color
        })
    
    return allocation

def generate_daily_spending(transactions, today):
    """Generate daily spending data for the dashboard"""
    daily_spending = []
    
    for i in range(7, 0, -1):
        day_date = today.date() - timedelta(days=i-1)
        day_str = day_date.isoformat()
        
        # Sum transactions for this day
        day_amount = sum(tx["amount"] for tx in transactions if tx["date"].startswith(day_str))
        
        daily_spending.append({
            "label": day_date.strftime("%b %d"),
            "amount": day_amount
        })
    
    return daily_spending

def calculate_avg_transaction(transactions, today):
    """Calculate average transaction amount for the current month"""
    month_transactions = [tx for tx in transactions if tx["date"].startswith(f"{today.year}-{today.month:02d}")]
    if not month_transactions:
        return 0
    
    total_amount = sum(tx["amount"] for tx in month_transactions)
    return total_amount / len(month_transactions)