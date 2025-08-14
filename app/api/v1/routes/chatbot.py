from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import json
import difflib
import re
import httpx
import os
import logging

logger = logging.getLogger(__name__)
from collections import defaultdict
import uuid
import asyncio

from app.api.deps import get_current_user
from typing import List
from app.core.auth import User
from app.schemas.chatbot import (
    ChatbotRequest,
    ChatbotResponse,
    ChatCommandRequest,
    ChatCommandResponse,
    ChatCommandPlan,
    ChatCommandAction,
    ExecutedActionResult,
)
from app.core.config import settings
from app.core.database import get_async_session
from app.crud.transaction import get_transactions_for_user, get_recent_transactions
from app.crud.category import get_categories_for_user
from app.utils.budgeting import calculate_goal_progress
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # Fallback handled below
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


@router.post("/command", response_model=ChatCommandResponse)
async def command_chatbot(
    request: Request,
    command_request: ChatCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Interpret a natural language command and execute corresponding actions
    (e.g., create a transaction). Uses OpenRouter to plan actions, then runs them.
    """
    try:
        # Establish current local time (Asia/Kolkata) for relative date interpretation
        kolkata_tz = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone(timedelta(hours=5, minutes=30))
        now_local = datetime.now(tz=kolkata_tz)

        # Fetch recent context for resolving references like "last transaction"
        user_id = uuid.UUID(str(current_user.id))
        recent = await get_recent_transactions(db, user_id, limit=30)
        recent_context = [
            {
                "id": str(tx.id),
                "description": tx.description,
                "amount": float(tx.amount),
                "category_name": (tx.category.name if tx.category else None),
                "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            }
            for tx in recent
        ]
        cats = await get_categories_for_user(user_id, db)
        categories_context = [c.name for c in cats]

        # Build system prompt describing available tools/actions and required params
        system_prompt = (
            "You are an action planner for Budget Pay. "
            "Translate the user's natural language command into a strictly JSON action plan. "
            "Only use supported actions. Always include ISO 8601 date-times. "
            "Respond with ONLY valid JSON, no extra commentary.\n\n"
            "Supported actions and required params: \n"
            "- create_transaction: {description: str, amount: float, transaction_date: ISO8601, category_name?: str} \n"
            "- update_transaction: {id: uuid, description?: str, amount?: float, transaction_date?: ISO8601, category_name?: str} \n"
            "- delete_transaction: {id: uuid} \n"
            "- create_category: {name: str, description?: str} \n"
            "- update_category: {id: uuid, name?: str, description?: str} \n"
            "- delete_category: {id: uuid} \n"
            "Rules: Interpret relative dates (e.g., 'yesterday', 'today') using the provided current datetime. "
            "If the command references 'last transaction' or similar, select an actual id from provided recent transactions. "
            "Never use placeholder values like <uuid>; always return concrete ids and dates."
        )

        user_prompt = (
            f"Command: {command_request.command}\n"
            f"Current datetime (Asia/Kolkata): {now_local.isoformat()}\n"
            f"Recent transactions (most recent first): {json.dumps(recent_context)}\n"
            f"Available categories: {json.dumps(categories_context)}\n"
            "Return JSON with shape: {\"actions\":[{\"type\":<action>,\"params\":{...}}]}"
        )

        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.BACKEND_BASE_URL,
            "X-Title": "Budget Pay Command Planner",
        }

        async def request_plan(model: str) -> dict:
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "model": model,
                "temperature": 0.0,
                "max_tokens": 512,
                "response_format": {"type": "json_object"}
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    return {"success": True, "data": resp.json()["choices"][0]["message"]["content"]}
                return {"success": False, "error": resp.text}

        result = await request_plan(PRIMARY_MODEL)
        if not result["success"]:
            result = await request_plan(FALLBACK_MODEL)
            if not result["success"]:
                raise HTTPException(status_code=500, detail=f"Planner failed: {result['error']}")

        # Parse JSON action plan
        try:
            plan_obj = json.loads(result["data"]) or {}
            raw_actions = plan_obj.get("actions", [])
        except Exception:
            raw_actions = []

        actions: List[ChatCommandAction] = []
        for a in raw_actions:
            try:
                actions.append(ChatCommandAction(**a))
            except Exception:
                # skip invalid action
                continue

        plan = ChatCommandPlan(actions=actions)
        executed: List[ExecutedActionResult] = []

        if not command_request.dry_run:
            for action in plan.actions:
                res = await _execute_action(action, current_user, db, command_request.command, recent_context, now_local)
                executed.append(res)
        else:
            executed = []

        # Compact natural language confirmation
        nl_response = _summarize_execution(command_request.command, plan, executed)

        return ChatCommandResponse(plan=plan, executed=executed, response=nl_response)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing command: {str(e)}",
        )

def _clean_amount(raw_amount) -> float:
    if raw_amount is None:
        return None  # type: ignore
    if isinstance(raw_amount, (int, float)):
        return float(raw_amount)
    cleaned = re.sub(r"[^0-9\.-]", "", str(raw_amount))
    return float(cleaned) if cleaned else None  # type: ignore


def _normalize_to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _date_from_relative(original_command: str, now_local: datetime) -> datetime | None:
    cmd = original_command.lower()
    if "yesterday" in cmd:
        target = now_local - timedelta(days=1)
        return target
    if "today" in cmd or "now" in cmd:
        return now_local
    if "tomorrow" in cmd:
        return now_local + timedelta(days=1)
    return None


async def _execute_action(action: ChatCommandAction, user: User, db: AsyncSession, original_command: str, recent_context: list, now_local: datetime) -> ExecutedActionResult:
    try:
        user_id = uuid.UUID(str(user.id))
        if action.type == "create_transaction":
            from app.schemas.transaction import TransactionCreate
            from app.crud.transaction import create_transaction_for_user
            from app.crud.category import get_category_by_name_for_user, create_category_for_user
            from app.schemas.category import CategoryCreate
            params = action.params
            description = params.get("description")
            amount = _clean_amount(params.get("amount"))
            transaction_date_str = params.get("transaction_date")
            category_name = params.get("category_name")
            if not description or amount is None or not transaction_date_str:
                return ExecutedActionResult(type=action.type, status="error", message="Missing required params: description, amount, transaction_date")
            try:
                # Prefer relative interpretation if present in the command
                rel = _date_from_relative(original_command, now_local)
                if rel is not None:
                    transaction_date = _normalize_to_naive_utc(rel)
                else:
                    transaction_date = datetime.fromisoformat(transaction_date_str)
                    transaction_date = _normalize_to_naive_utc(transaction_date)
            except Exception:
                return ExecutedActionResult(type=action.type, status="error", message="transaction_date must be ISO 8601")

            category_id = None
            if category_name:
                existing = await get_category_by_name_for_user(category_name, user_id, db)
                if existing is None:
                    new_cat = await create_category_for_user(user_id, CategoryCreate(name=category_name, description=None, default_percentage=0.0, custom_percentage=None, is_default=False, is_fixed=False), db)
                    category_id = new_cat.id
                else:
                    category_id = existing.id

            tx = await create_transaction_for_user(user_id, TransactionCreate(description=description, amount=amount, category_id=category_id, transaction_date=transaction_date), db)
            return ExecutedActionResult(type=action.type, status="success", message="Transaction created", data={"transaction_id": str(tx.id)})

        elif action.type == "update_transaction":
            from app.crud.transaction import get_transaction_by_id, update_transaction
            from app.schemas.transaction import TransactionUpdate
            params = action.params
            tx_id_raw = params.get("id")
            tx = None
            resolved_id = None
            if tx_id_raw and isinstance(tx_id_raw, str) and tx_id_raw.startswith("<"):
                tx_id_raw = None
            if tx_id_raw:
                try:
                    resolved_id = uuid.UUID(str(tx_id_raw))
                except Exception:
                    resolved_id = None
            if resolved_id is None:
                # Try resolving from context for phrases like "last transaction" or description keywords
                cmd = original_command.lower()
                candidate = None
                # naive keyword heuristic: pick any word in command that appears in a recent description
                words = [w for w in re.findall(r"[a-zA-Z]+", cmd) if len(w) >= 3]
                for txc in recent_context:
                    desc = (txc.get("description") or "").lower()
                    if any(w in desc for w in words):
                        candidate = txc
                        break
                if candidate is None and recent_context:
                    candidate = recent_context[0]
                if candidate is not None:
                    resolved_id = uuid.UUID(candidate["id"])  # may raise
            if resolved_id is None:
                return ExecutedActionResult(type=action.type, status="error", message="Unable to resolve transaction id")
            tx = await get_transaction_by_id(resolved_id, user_id, db)
            if tx is None:
                return ExecutedActionResult(type=action.type, status="error", message="Transaction not found")
            update_payload = {}
            if "description" in params:
                update_payload["description"] = params["description"]
            if "amount" in params:
                update_payload["amount"] = _clean_amount(params["amount"])
            if "transaction_date" in params:
                # If placeholder provided or relative date in command, override
                if isinstance(params["transaction_date"], str) and params["transaction_date"].startswith("<"):
                    dt = _date_from_relative(original_command, now_local) or now_local
                else:
                    dt = datetime.fromisoformat(params["transaction_date"])  # may raise
                dt = _normalize_to_naive_utc(dt)
            if "category_name" in params and params["category_name"]:
                from app.crud.category import get_category_by_name_for_user, create_category_for_user
                from app.schemas.category import CategoryCreate
                cat = await get_category_by_name_for_user(params["category_name"], user_id, db)
                if cat is None:
                    cat = await create_category_for_user(user_id, CategoryCreate(name=params["category_name"], description=None, default_percentage=0.0, custom_percentage=None, is_default=False, is_fixed=False), db)
                update_payload["category_id"] = cat.id
            tx_updated = await update_transaction(tx, TransactionUpdate(**update_payload), db)
            return ExecutedActionResult(type=action.type, status="success", message="Transaction updated", data={"transaction_id": str(tx_updated.id)})

        elif action.type == "delete_transaction":
            from app.crud.transaction import get_transaction_by_id, delete_transaction
            params = action.params
            tx_id_raw = params.get("id")
            resolved_id = None
            if tx_id_raw and isinstance(tx_id_raw, str) and tx_id_raw.startswith("<"):
                tx_id_raw = None
            if tx_id_raw:
                try:
                    resolved_id = uuid.UUID(str(tx_id_raw))
                except Exception:
                    resolved_id = None
            if resolved_id is None:
                # Resolve "last transaction" from recent context
                candidate = recent_context[0] if recent_context else None
                if candidate is None:
                    return ExecutedActionResult(type=action.type, status="error", message="Unable to resolve transaction id")
                resolved_id = uuid.UUID(candidate["id"])  # may raise
            tx = await get_transaction_by_id(resolved_id, user_id, db)
            if tx is None:
                return ExecutedActionResult(type=action.type, status="error", message="Transaction not found")
            await delete_transaction(tx, db)
            return ExecutedActionResult(type=action.type, status="success", message="Transaction deleted", data={"transaction_id": str(tx.id)})

        elif action.type == "create_category":
            from app.schemas.category import CategoryCreate
            from app.crud.category import create_category_for_user, get_category_by_name_for_user
            params = action.params
            name = params.get("name")
            description = params.get("description")
            if not name:
                return ExecutedActionResult(type=action.type, status="error", message="Missing name")
            existing = await get_category_by_name_for_user(name, user_id, db)
            if existing:
                return ExecutedActionResult(type=action.type, status="success", message="Category already exists", data={"category_id": str(existing.id)})
            cat = await create_category_for_user(user_id, CategoryCreate(name=name, description=description, default_percentage=0.0, custom_percentage=None, is_default=False, is_fixed=False), db)
            return ExecutedActionResult(type=action.type, status="success", message="Category created", data={"category_id": str(cat.id)})

        elif action.type == "update_category":
            from app.crud.category import get_category_by_id, update_category, get_category_by_name_for_user, get_categories_for_user
            from app.schemas.category import CategoryUpdate
            params = action.params
            cat_id_raw = params.get("id")
            cat = None
            # Try by ID first if provided and non-placeholder
            if cat_id_raw and isinstance(cat_id_raw, str) and not cat_id_raw.startswith("<"):
                try:
                    cat_uuid = uuid.UUID(str(cat_id_raw))
                    cat = await get_category_by_id(cat_uuid, user_id, db)
                except Exception:
                    cat = None
            # Fallback: try by name if provided
            if cat is None:
                desired_name = params.get("name")
                if desired_name:
                    cat = await get_category_by_name_for_user(desired_name, user_id, db)
            # Fuzzy fallback: pick closest existing category by name
            if cat is None:
                user_cats = await get_categories_for_user(user_id, db)
                names = [c.name for c in user_cats]
                desired_name = params.get("name") or ""
                if names and desired_name:
                    match = difflib.get_close_matches(desired_name, names, n=1, cutoff=0.6)
                    if match:
                        # Fetch again by name to get entity
                        cat = await get_category_by_name_for_user(match[0], user_id, db)
            if cat is None:
                return ExecutedActionResult(type=action.type, status="error", message="Category not found")
            update_obj = CategoryUpdate(
                name=params.get("name"),
                description=params.get("description"),
            )
            cat_updated = await update_category(cat, update_obj, db)
            return ExecutedActionResult(type=action.type, status="success", message="Category updated", data={"category_id": str(cat_updated.id)})

        elif action.type == "delete_category":
            from app.crud.category import get_category_by_id, delete_category
            params = action.params
            cat_id = params.get("id")
            if not cat_id:
                return ExecutedActionResult(type=action.type, status="error", message="Missing id")
            cat = await get_category_by_id(uuid.UUID(str(cat_id)), user_id, db)
            if cat is None:
                return ExecutedActionResult(type=action.type, status="error", message="Category not found")
            await delete_category(cat, db)
            return ExecutedActionResult(type=action.type, status="success", message="Category deleted", data={"category_id": str(cat.id)})

        return ExecutedActionResult(type=action.type, status="error", message="Unsupported action type")
    except Exception as e:
        return ExecutedActionResult(type=action.type, status="error", message=str(e))


def _summarize_execution(command: str, plan: ChatCommandPlan, executed: List[ExecutedActionResult]) -> str:
    if not plan.actions:
        return "I couldn't determine any valid action from your command."
    if not executed:
        return "Planned actions without execution (dry run)."
    successes = [e for e in executed if e.status == "success"]
    errors = [e for e in executed if e.status == "error"]
    if successes and not errors:
        return "Done."
    if successes and errors:
        return "Partially completed."
    return "Could not complete the requested action."

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