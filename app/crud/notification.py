# app/crud/notification.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationUpdate
from typing import List
import uuid

async def create_notification(db: AsyncSession, notification: NotificationCreate) -> Notification:
    db_notification = Notification(**notification.dict())
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    return db_notification

async def get_notifications_for_user(db: AsyncSession, user_id: uuid.UUID) -> List[Notification]:
    result = await db.execute(
        select(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    )
    return result.scalars().all()

async def mark_notification_as_read(db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification:
    result = await db.execute(
        select(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
    )
    notification = result.scalars().first()
    
    if notification:
        notification.is_read = True
        await db.commit()
        await db.refresh(notification)
    return notification

async def mark_all_notifications_as_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount