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
            {json.dumps(context, indent=2)}
            
            Focus on useful, actionable insights about their spending patterns, savings progress, or budget category performance.
            Highlight opportunities to save money or better allocate their budget.
            If there's a category where they're overspending, mention it specifically.
            If they're doing well with savings, acknowledge and encourage that.
            
            Respond with:
            Title: [Catchy, emoji-friendly title about their budget/spending]
            Message: [Detailed but concise insight with specific figures when available]
            """
        elif notification_type == "saving_tip":
            user_prompt = f"""
            Generate a personalized money-saving tip for a user with these spending habits:
            {json.dumps(context, indent=2)}
            
            Focus on practical, specific advice based on their actual spending patterns.
            Identify categories where they could cut back.
            If they spend a lot on a specific category, suggest a realistic way to save.
            Use actual numbers from their data when suggesting savings.
            
            Respond with:
            Title: [Catchy, emoji-friendly saving tip title]
            Message: [Specific, actionable saving tip with numbers/percentages]
            """
        elif notification_type == "goal_progress":
            user_prompt = f"""
            Create an encouraging notification about progress toward financial goals:
            {json.dumps(context, indent=2)}
            
            Focus on their savings goal progress and what they need to do to stay on track.
            Be motivational but realistic about their current pace.
            Include specific numbers about their progress and what's needed to reach their goal.
            
            Respond with:
            Title: [Catchy, emoji-friendly goal progress title]
            Message: [Motivational message with specific figures about their progress]
            """
        else:
            user_prompt = f"""
            Create a helpful financial notification based on this user data:
            {json.dumps(context, indent=2)}
            
            Focus on whatever insight would be most valuable to this user based on their data.
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
                    "model": "meta-llama/llama-3.2-3b-instruct",  # Using a more capable model
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,  # Slightly more creative
                    "max_tokens": 256
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
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
                    
                    # Create notification
                    notification = NotificationCreate(
                        user_id=user_id,
                        title=title[:100],  # Allow longer titles
                        message=message[:500],  # Allow longer messages
                        type=notification_type,
                        status="info",
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