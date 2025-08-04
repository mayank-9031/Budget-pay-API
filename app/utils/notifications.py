# app/utils/notifications.py
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.notification import NotificationCreate
from app.crud.notification import create_notification
import uuid
import httpx
from app.core.config import settings
import json
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

# Store active WebSocket connections by user_id
active_connections: Dict[uuid.UUID, List[WebSocket]] = {}

# Example: status can be 'alert', 'completed', etc. Type can be 'overspend', 'milestone', etc.
async def notify_overspend(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID, category_name: str, overspend_amt: float) -> None:
    notification = NotificationCreate(
        user_id=user_id,
        title="Overspending Alert",
        message=f"You have overspent {overspend_amt} in {category_name} category.",
        type="overspend",
        status="alert",
        category_id=category_id
    )
    notification_obj = await create_notification(db, notification)
    
    # Send real-time notification if user is connected
    await send_realtime_notification(user_id, notification_obj)

async def notify_savings_milestone(db: AsyncSession, user_id: uuid.UUID, saved_amt: float, target: float) -> None:
    notification = NotificationCreate(
        user_id=user_id,
        title="Savings Milestone Achieved!",
        message=f"Congratulations! You've saved {saved_amt} out of your target {target}.",
        type="milestone",
        status="completed",
        category_id=None
    )
    notification_obj = await create_notification(db, notification)
    
    # Send real-time notification if user is connected
    await send_realtime_notification(user_id, notification_obj)

async def generate_ai_notification(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    context: Dict[str, Any],
    notification_type: str
) -> Optional[Dict]:
    """
    Generate personalized notification using OpenRouter API based on user activity
    
    Args:
        db: Database session
        user_id: Target user ID
        context: Contextual information for AI to generate relevant notification
        notification_type: Type of notification to generate (e.g., 'budget_insight', 'saving_tip')
        
    Returns:
        Created notification object or None if generation failed
    """
    if not settings.OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not configured. Skipping AI notification generation.")
        return None
        
    try:
        # System prompt for all notification types
        system_prompt = """
        You are a cool, Gen-Z financial assistant for the Budget Pay app that creates engaging, personalized notifications.
        
        Your notifications have two parts:
        1. Title: A catchy, attention-grabbing headline (2-6 words)
        2. Message: A brief, personalized insight or tip (1-3 sentences)
        
        Follow these guidelines:
        - Use emojis appropriately (1-2 per notification)
        - Be concise but specific
        - Use Gen-Z friendly language (but stay professional)
        - Make insights actionable and relevant to the user's data
        - Focus on real patterns in their spending/saving behavior
        - Format monetary values with the ₹ symbol (e.g., ₹5,000)
        - Be encouraging and supportive, never judgmental
        - If suggesting savings, be specific about how much and where
        
        Response format:
        Title: [Your catchy title here]
        Message: [Your detailed notification message here]
        
        The Title and Message should be clearly labeled as shown above.
        """
        
        # Build user prompt based on notification type
        if notification_type == "budget_insight":
            user_prompt = f"""
            Create a personalized budget insight notification based on this user data:
            
            User financial overview:
            - Monthly income: ₹{context['financial_overview']['monthly_income']}
            - Spent so far this month: ₹{context['financial_overview']['total_spent']}
            - Remaining budget: ₹{context['financial_overview']['remaining_budget']}
            - Percent of budget used: {context['financial_overview']['percent_budget_used']:.1f}%
            - Days left in month: {context['time_info']['days_left_in_month']}
            - Month progress: {context['financial_overview']['month_progress_percent']:.1f}%
            
            Top spending categories:
            {', '.join([f"{cat['name']}: ₹{cat['amount']}" for cat in context['spending_patterns']['top_categories'][:2]])}
            
            Focus on useful, actionable insights about their spending patterns, budget allocation, or month-to-date spending vs. month progress.
            
            Respond with:
            Title: [Catchy, emoji-friendly title about their budget/spending]
            Message: [Detailed but concise insight with specific figures when available]
            """
        elif notification_type == "saving_tip":
            user_prompt = f"""
            Generate a personalized money-saving tip for this user:
            
            User financial overview:
            - Monthly income: ₹{context['financial_overview']['monthly_income']}
            - Spent so far: ₹{context['financial_overview']['total_spent']}
            - Top spending categories: {', '.join([f"{cat['name']}: ₹{cat['amount']}" for cat in context['spending_patterns']['top_categories'][:2]])}
            
            Category breakdown:
            {', '.join([f"{cat['name']}: ₹{cat['spending']} (allocated: ₹{cat['allocated']})" for cat in context['categories'][:3]])}
            
            Focus on the category where they could save the most money, with a specific and practical tip.
            Suggest a realistic amount they could save by following your tip.
            
            Respond with:
            Title: [Catchy, emoji-friendly saving tip title]
            Message: [Specific, actionable saving tip with numbers/percentages]
            """
        elif notification_type == "goal_progress":
            user_prompt = f"""
            Create an encouraging notification about this user's savings goal progress:
            
            Monthly savings goal: ₹{context['savings_goals']['monthly']['goal_amount']}
            Current progress: ₹{context['savings_goals']['monthly']['saved_amount']} ({context['savings_goals']['monthly']['progress_percentage']:.1f}%)
            Status: {context['savings_goals']['monthly']['status']}
            Month progress: {context['financial_overview']['month_progress_percent']:.1f}%
            
            Focus on:
            1. Current progress relative to month completion
            2. Specific amount needed to stay on track 
            3. Encouragement that's motivational but realistic
            
            If they're behind target, suggest a specific action they can take.
            If they're on track, celebrate their progress and encourage consistency.
            
            Respond with:
            Title: [Catchy, emoji-friendly goal progress title]
            Message: [Motivational message with specific figures about their progress]
            """
        elif notification_type == "spending_alert":
            # Find the most overspent category
            most_overspent = None
            if context['spending_patterns']['overspent_categories']:
                most_overspent = max(context['spending_patterns']['overspent_categories'], key=lambda x: x['overspent_by'])
            
            user_prompt = f"""
            Create an alert notification about overspending:
            
            {'Most overspent category: ' + most_overspent['name'] + ', overspent by ₹' + str(most_overspent['overspent_by']) if most_overspent else 'User has multiple overspent categories'}
            Overspent categories: {', '.join([f"{cat['name']}: overspent by ₹{cat['overspent_by']}" for cat in context['spending_patterns']['overspent_categories'][:3]])}
            Days left in month: {context['time_info']['days_left_in_month']}
            Remaining budget: ₹{context['financial_overview']['remaining_budget']}
            
            Create an alert that:
            1. Highlights the specific overspending issue
            2. Mentions the amount overspent
            3. Suggests a specific action to take
            4. Is helpful but not judgmental
            
            Respond with:
            Title: [Catchy, emoji-friendly alert title]
            Message: [Specific alert message with amounts and action suggestion]
            """
        elif notification_type == "activity_reminder":
            user_prompt = f"""
            Create a friendly reminder notification for a user who hasn't logged any transactions in the past 24 hours:
            
            Current date: {context['time_info']['current_date']} ({context['time_info']['day_of_week']})
            Last transaction: {context['transaction_history']['recent_transactions'][0]['date'] if context['transaction_history']['recent_transactions'] else 'None recent'}
            Remaining budget: ₹{context['financial_overview']['remaining_budget']}
            Days left in month: {context['time_info']['days_left_in_month']}
            
            Create a gentle reminder that:
            1. Encourages the user to log their recent transactions
            2. Emphasizes the importance of tracking for budget success
            3. Is friendly and motivational, not pushy
            
            Respond with:
            Title: [Catchy, emoji-friendly reminder title]
            Message: [Friendly reminder message]
            """
        else:
            user_prompt = f"""
            Create a helpful financial notification for this user:
            
            Monthly income: ₹{context['user']['monthly_income']}
            Spent this month: ₹{context['financial_overview']['total_spent']}
            Remaining: ₹{context['financial_overview']['remaining_budget']}
            Days left in month: {context['time_info']['days_left_in_month']}
            
            Focus on whatever insight would be most valuable based on their data.
            Be specific and actionable in your advice.
            
            Respond with:
            Title: [Catchy, emoji-friendly financial insight title]
            Message: [Specific, actionable financial insight with numbers]
            """
        
        # Call OpenRouter API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": settings.BACKEND_BASE_URL,  # Required for OpenRouter API
                    "X-Title": "Budget Pay Notification Generator"  # Optional but recommended
                },
                json={
                    "model": "deepseek/deepseek-chat-v3-0324:free",  # Primary model
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,  # Slightly more creative
                    "max_tokens": 256
                },
                timeout=15.0
            )
            
            # Try with primary model first
            if response.status_code == 200:
                result = response.json()
                ai_message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                # If primary model fails, try fallback model
                logger.warning(f"Primary model failed. Trying fallback model deepseek/deepseek-chat-v3-0324:free")
                try:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": settings.BACKEND_BASE_URL,
                            "X-Title": "Budget Pay Notification Generator"
                        },
                        json={
                            "model": "meta-llama/llama-3.2-3b-instruct",  # Fallback model
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            "temperature": 0.7,
                            "max_tokens": 256
                        },
                        timeout=15.0
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        ai_message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    else:
                        logger.error(f"Both models failed. Last error: {response.text}")
                        return None
                except Exception as e:
                    logger.error(f"Error with fallback model: {str(e)}")
                    return None
            
            # Process AI message if we have one
            if ai_message:
                    # Parse the AI response
                    title = ""
                    message = ""
                    
                    # Extract title and message using the expected format
                    if "Title:" in ai_message and "Message:" in ai_message:
                        title_start = ai_message.index("Title:") + 6
                        message_start = ai_message.index("Message:") + 8
                        title = ai_message[title_start:message_start].strip()
                        message = ai_message[message_start:].strip()
                    else:
                        # Fallback parsing if format isn't followed
                        lines = ai_message.strip().split("\n")
                        title = next((line.replace("Title:", "").strip() for line in lines if line.startswith("Title:")), "Budget Insight")
                        message_lines = [line.replace("Message:", "").strip() for line in lines if line.startswith("Message:") or not line.startswith("Title:")]
                        message = " ".join(message_lines).strip()
                    
                    # Determine status based on notification type
                    status = "info"
                    if notification_type == "spending_alert":
                        status = "alert"
                    elif notification_type == "activity_reminder":
                        status = "reminder"
                    elif notification_type == "goal_progress" and "achieved" in message.lower():
                        status = "completed"
                    
                    # Create notification
                    notification = NotificationCreate(
                        user_id=user_id,
                        title=title[:100],  # Allow longer titles
                        message=message[:500],  # Allow longer messages
                        type=notification_type,
                        status=status,
                        category_id=context.get("category_id")
                    )
                    notification_obj = await create_notification(db, notification)
                    
                    # Send real-time notification if user is connected
                    await send_realtime_notification(user_id, notification_obj)
                    
                    return notification_obj
            
            logger.warning(f"OpenRouter API call failed with status {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating AI notification: {str(e)}")
        return None

# WebSocket connection management
def connect_user(websocket: WebSocket, user_id: uuid.UUID):
    """Register a new WebSocket connection for a user"""
    if user_id not in active_connections:
        active_connections[user_id] = []
    active_connections[user_id].append(websocket)
    logger.info(f"User {user_id} connected. Total connections: {len(active_connections[user_id])}")

def disconnect_user(websocket: WebSocket, user_id: uuid.UUID):
    """Remove a WebSocket connection for a user"""
    if user_id in active_connections:
        if websocket in active_connections[user_id]:
            active_connections[user_id].remove(websocket)
        
        # Clean up if no connections left
        if not active_connections[user_id]:
            del active_connections[user_id]
            
    logger.info(f"User {user_id} disconnected. Remaining connections: {len(active_connections.get(user_id, []))}")

async def send_realtime_notification(user_id: uuid.UUID, notification: Any):
    """Send a notification to a user via WebSocket if they're connected"""
    if user_id not in active_connections:
        return
        
    # Convert notification to dict for serialization
    if hasattr(notification, "__dict__"):
        notification_data = {
            "id": str(notification.id),
            "title": notification.title,
            "message": notification.message,
            "type": notification.type,
            "status": notification.status,
            "created_at": notification.created_at.isoformat() if hasattr(notification, "created_at") else datetime.utcnow().isoformat(),
        }
    else:
        notification_data = notification
    
    # Send to all active connections for this user
    dead_connections = []
    for websocket in active_connections[user_id]:
        try:
            await websocket.send_json({
                "type": "notification",
                "data": notification_data
            })
        except Exception as e:
            logger.error(f"Failed to send to websocket: {str(e)}")
            dead_connections.append(websocket)
    
    # Clean up dead connections
    for dead in dead_connections:
        if dead in active_connections[user_id]:
            active_connections[user_id].remove(dead)