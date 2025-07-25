# app/api/v1/routes/notification.py
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, BackgroundTasks, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from app.schemas.notification import NotificationRead, NotificationCreate, NotificationUpdate
from app.crud import notification as crud_notification
from app.crud import transaction as crud_transaction
from app.crud import category as crud_category
from app.api import deps
from uuid import UUID
from app.core.database import get_async_session
from app.utils.notifications import connect_user, disconnect_user, generate_ai_notification
from app.core.auth import User
from app.crud import user as crud_user
from app.utils.budgeting import calculate_goal_progress
from datetime import datetime, timedelta
import calendar
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[NotificationRead])
async def get_notifications(
    unread_only: bool = Query(False, description="Filter to only unread notifications"),
    limit: int = Query(50, description="Maximum number of notifications to return"),
    db: AsyncSession = Depends(get_async_session), 
    current_user: User = Depends(deps.get_current_user)
):
    """Get notifications for the current user with optional filtering"""
    return await crud_notification.get_notifications_for_user(
        db, 
        user_id=current_user.id, 
        unread_only=unread_only,
        limit=limit
    )

@router.get("/unread-count", response_model=int)
async def get_unread_count(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(deps.get_current_user)
):
    """Get count of unread notifications for the current user"""
    return await crud_notification.get_unread_count(db, current_user.id)

@router.get("/{notification_id}", response_model=NotificationRead)
async def get_notification(
    notification_id: UUID, 
    db: AsyncSession = Depends(get_async_session), 
    current_user: User = Depends(deps.get_current_user)
):
    """Get a specific notification, ensuring it belongs to the current user"""
    notification = await crud_notification.get_notification_by_id(db, notification_id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_as_read(
    notification_id: UUID, 
    db: AsyncSession = Depends(get_async_session), 
    current_user: User = Depends(deps.get_current_user)
):
    """Mark a specific notification as read, ensuring it belongs to the current user"""
    notification = await crud_notification.mark_notification_as_read(db, notification_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.post("/read_all", response_model=int)
async def mark_all_notifications_as_read(
    db: AsyncSession = Depends(get_async_session), 
    current_user: User = Depends(deps.get_current_user)
):
    """Mark all notifications for the current user as read"""
    return await crud_notification.mark_all_notifications_as_read(db, current_user.id)

@router.post("/generate-ai", response_model=Optional[NotificationRead])
async def create_ai_notification(
    context: Dict[str, Any] = Body(...),
    notification_type: str = Query(..., description="Type of AI notification to generate"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(deps.get_current_user)
):
    """Generate an AI-powered notification based on user data"""
    # Add user context data
    context["user_id"] = str(current_user.id)
    
    # If we want immediate response
    notification = await generate_ai_notification(
        db=db,
        user_id=current_user.id,
        context=context,
        notification_type=notification_type
    )
    
    if notification:
        return notification
    else:
        raise HTTPException(
            status_code=503, 
            detail="Unable to generate AI notification. Service may be unavailable."
        )

@router.post("/generate-budget-insight", response_model=Optional[NotificationRead])
async def generate_budget_insight(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(deps.get_current_user)
):
    """Generate personalized budget insight based on recent transactions and categories"""
    try:
        # Get user's transaction data
        transactions = await crud_transaction.get_recent_transactions(db, current_user.id, limit=30)
        categories = await crud_category.get_categories_for_user(current_user.id, db)
        
        # Get current date information
        today = datetime.now()
        start_of_month = datetime(today.year, today.month, 1)
        end_of_month = datetime(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        start_of_week = (today - timedelta(days=today.weekday()))
        end_of_week = (start_of_week + timedelta(days=6))
        
        # Safe float conversion
        def safe_float(value, default=0):
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Basic user info
        monthly_income = safe_float(getattr(current_user, "monthly_income", 0))
        savings_goal_amount = safe_float(getattr(current_user, "savings_goal_amount", 0))
        
        # Calculate spending for current month
        current_month_spending = sum(
            safe_float(tx.amount) for tx in transactions 
            if tx.transaction_date and tx.transaction_date.month == today.month and tx.transaction_date.year == today.year
        )
        
        # Calculate remaining budget
        remaining_budget = monthly_income - current_month_spending
        
        # Calculate goal progress data
        goal_progress = await calculate_goal_progress(current_user, "monthly", db)
        
        # Calculate category spending
        category_spending = {}
        for cat in categories:
            cat_id = str(cat.id)
            cat_spending = sum(
                safe_float(tx.amount) for tx in transactions 
                if tx.category_id == cat.id and tx.transaction_date and 
                tx.transaction_date.month == today.month and tx.transaction_date.year == today.year
            )
            
            # Calculate allocated budget for this category
            budget_percentage = safe_float(cat.custom_percentage if hasattr(cat, 'custom_percentage') and cat.custom_percentage is not None 
                                         else cat.default_percentage)
            allocated = monthly_income * (budget_percentage / 100) if budget_percentage > 0 else 0
            
            # Calculate remaining budget and status
            remaining = allocated - cat_spending
            status = "On Track"
            if remaining < 0:
                status = "Over Budget"
            elif remaining <= allocated * 0.1:  # Within 10% of budget
                status = "Near Limit"
                
            category_spending[cat.name] = {
                "id": cat_id,
                "name": cat.name,
                "spending": cat_spending,
                "allocated": allocated,
                "remaining": remaining,
                "status": status,
                "percentage_used": (cat_spending / allocated * 100) if allocated > 0 else 0
            }
        
        # Find top spending categories
        top_categories = sorted(
            [(cat_name, data["spending"]) for cat_name, data in category_spending.items()],
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        # Find overspent categories
        overspent_categories = [
            (cat_name, data["spending"] - data["allocated"]) 
            for cat_name, data in category_spending.items() 
            if data["status"] == "Over Budget"
        ]
        
        # Build context data
        context = {
            "user": {
                "id": str(current_user.id),
                "full_name": getattr(current_user, "full_name", "") or "",
                "monthly_income": monthly_income,
                "savings_goal_amount": savings_goal_amount
            },
            "financial_overview": {
                "monthly_income": monthly_income,
                "total_spent": current_month_spending,
                "remaining_budget": remaining_budget,
                "percent_budget_used": (current_month_spending / monthly_income * 100) if monthly_income > 0 else 0,
                "days_left_in_month": (end_of_month.date() - today.date()).days,
                "daily_budget_remaining": remaining_budget / max(1, (end_of_month.date() - today.date()).days) if remaining_budget > 0 else 0,
                "month_progress_percent": (today.day / calendar.monthrange(today.year, today.month)[1]) * 100
            },
            "savings": {
                "goal_amount": savings_goal_amount,
                "saved_amount": goal_progress["saved_amount"],
                "progress_percentage": goal_progress["progress_percentage"],
                "status": goal_progress["status"],
                "remaining_amount": goal_progress["remaining_amount"]
            },
            "spending_patterns": {
                "top_categories": [{"name": name, "amount": amount} for name, amount in top_categories],
                "overspent_categories": [{"name": name, "overspent_by": amount} for name, amount in overspent_categories],
                "total_categories": len(categories),
                "active_categories": len([c for c in category_spending.values() if c["spending"] > 0])
            },
            "transaction_history": {
                "total_transactions": len(transactions),
                "recent_transactions": [
                    {
                        "amount": safe_float(tx.amount),
                        "description": tx.description,
                        "date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                        "category": tx.category.name if tx.category else "Uncategorized"
                    }
                    for tx in transactions[:5]  # Just the 5 most recent
                ]
            },
            "categories": [
                {
                    "name": cat_name,
                    "spending": data["spending"],
                    "allocated": data["allocated"],
                    "remaining": data["remaining"],
                    "status": data["status"],
                    "percentage_used": data["percentage_used"]
                }
                for cat_name, data in category_spending.items()
            ],
            "date_info": {
                "current_date": today.date().isoformat(),
                "current_month": today.strftime("%B %Y"),
                "start_of_month": start_of_month.date().isoformat(),
                "end_of_month": end_of_month.date().isoformat()
            }
        }
        
        # Generate AI notification
        notification = await generate_ai_notification(
            db=db,
            user_id=current_user.id,
            context=context,
            notification_type="budget_insight"
        )
        
        if notification:
            return notification
        else:
            raise HTTPException(
                status_code=503, 
                detail="Unable to generate AI notification. Service may be unavailable."
            )
            
    except Exception as e:
        logger.error(f"Error generating budget insight: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error generating budget insight: {str(e)}"
        )

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_async_session)
):
    """WebSocket endpoint for real-time notifications"""
    try:
        # Authenticate user from token
        user = await deps.get_current_user_from_token(token, db)
        if not user:
            await websocket.close(code=4001, reason="Authentication failed")
            return
            
        # Accept the connection
        await websocket.accept()
        
        # Register the connection
        connect_user(websocket, user.id)
        
        try:
            # Keep the connection alive and handle messages
            while True:
                data = await websocket.receive_text()
                # Currently just echo any received messages
                # In the future could process commands
                await websocket.send_json({"status": "received", "timestamp": datetime.now().isoformat()})
                
        except WebSocketDisconnect:
            # Handle normal disconnection
            disconnect_user(websocket, user.id)
            
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.close(code=4000, reason="Server error")
        except:
            pass