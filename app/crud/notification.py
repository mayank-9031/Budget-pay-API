# app/crud/notification.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc, func
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationUpdate
from typing import List, Optional
import uuid
from datetime import datetime, timedelta

async def create_notification(db: AsyncSession, notification: NotificationCreate) -> Notification:
    """Create a new notification"""
    # Apply IST timezone to creation timestamp (UTC+5:30)
    utc_now = datetime.utcnow()
    ist_offset = timedelta(hours=5, minutes=30)
    ist_now = utc_now + ist_offset
    
    notification_dict = notification.dict()
    db_notification = Notification(**notification_dict, created_at=ist_now)
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    return db_notification

async def get_notification_by_id(db: AsyncSession, notification_id: uuid.UUID) -> Optional[Notification]:
    """Get a specific notification by ID"""
    result = await db.execute(
        select(Notification)
        .filter(Notification.id == notification_id)
    )
    return result.scalars().first()

async def get_notifications_for_user(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    unread_only: bool = False,
    limit: int = 50
) -> List[Notification]:
    """Get notifications for a specific user with filtering options"""
    query = (
        select(Notification)
        .filter(Notification.user_id == user_id)
    )
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
        
    query = query.order_by(desc(Notification.created_at)).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Get count of unread notifications for a user"""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
    )
    return result.scalar_one() or 0

async def mark_notification_as_read(db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Notification]:
    """Mark a notification as read, ensuring it belongs to the specified user"""
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
    """Mark all notifications as read for a specific user"""
    result = await db.execute(
        update(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount

async def delete_notification(db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete a notification, ensuring it belongs to the specified user"""
    result = await db.execute(
        delete(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
    )
    await db.commit()
    return result.rowcount > 0

async def update_notification(
    db: AsyncSession, 
    notification_id: uuid.UUID, 
    user_id: uuid.UUID,
    update_data: NotificationUpdate
) -> Optional[Notification]:
    """Update a notification's fields, ensuring it belongs to the specified user"""
    result = await db.execute(
        select(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
    )
    notification = result.scalars().first()
    
    if notification:
        update_dict = update_data.dict(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(notification, key, value)
            
        await db.commit()
        await db.refresh(notification)
        
    return notification