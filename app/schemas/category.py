# app/schemas/category.py
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    budget_limit: Optional[float] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_fixed: Optional[bool] = False

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    budget_limit: Optional[float] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_fixed: Optional[bool] = None

class Category(CategoryBase):
    id: int
    user_id: str

    class Config:
        from_attributes = True

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    budget_limit: Optional[float] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_fixed: bool = False

    class Config:
        from_attributes = True
