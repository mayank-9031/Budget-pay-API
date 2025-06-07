# app/schemas/category.py
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class CategoryBase(BaseModel):
    name: str = Field(..., description="Category name, e.g. Food, Transport")
    description: Optional[str]
    default_percentage: Optional[float] = Field(..., description="Suggested percent allocation (0–100)")
    custom_percentage: Optional[float] = Field(None, description="User override % (0–100)")
    is_default: Optional[bool] = False

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_percentage: Optional[float] = None
    custom_percentage: Optional[float] = None
    is_default: Optional[bool] = None

    class Config:
        # Only fields provided in the request will be validated/used
        extra = "ignore"
        orm_mode = True

class CategoryRead(CategoryBase):
    id: uuid.UUID
    user_id: uuid.UUID

    class Config:
        orm_mode = True
