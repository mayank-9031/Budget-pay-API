# app/api/v1/routes/notification.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.schemas.notification import NotificationRead
from app.crud import notification as crud_notification
from app.api import deps
from uuid import UUID
from app.core.database import get_async_session

router = APIRouter()

@router.get("/", response_model=List[NotificationRead])
async def get_notifications(
    db: AsyncSession = Depends(get_async_session), 
    current_user = Depends(deps.get_current_user)
):
    return await crud_notification.get_notifications_for_user(db, user_id=current_user.id)

@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_as_read(
    notification_id: UUID, 
    db: AsyncSession = Depends(get_async_session), 
    current_user = Depends(deps.get_current_user)
):
    notification = await crud_notification.mark_notification_as_read(db, notification_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.post("/read_all", response_model=int)
async def mark_all_notifications_as_read(
    db: AsyncSession = Depends(get_async_session), 
    current_user = Depends(deps.get_current_user)
):
    return await crud_notification.mark_all_notifications_as_read(db, current_user.id)