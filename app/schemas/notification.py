from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class NotificationBase(BaseModel):
    title: str
    message: str
    type: str
    status: str
    category_id: Optional[uuid.UUID] = None

class NotificationCreate(NotificationBase):
    user_id: uuid.UUID

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None

class NotificationRead(NotificationBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_read: bool
    created_at: datetime
    category_id: Optional[uuid.UUID]

    class Config:
        from_attributes = True 