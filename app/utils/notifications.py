# app/utils/notifications.py
from typing import Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.notification import NotificationCreate
from app.crud.notification import create_notification
import uuid

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
    await create_notification(db, notification)

async def notify_savings_milestone(db: AsyncSession, user_id: uuid.UUID, saved_amt: float, target: float) -> None:
    notification = NotificationCreate(
        user_id=user_id,
        title="Savings Milestone Achieved!",
        message=f"Congratulations! You've saved {saved_amt} out of your target {target}.",
        type="milestone",
        status="completed",
        category_id=None
    )
    await create_notification(db, notification)