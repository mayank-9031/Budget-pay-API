# app/models/category.py
import uuid
from sqlalchemy import Column, String, ForeignKey, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(length=100), nullable=False)
    description = Column(String(length=255), nullable=True)
    # Default percentage (according to 50/30/20 rule or user‐customized)
    default_percentage = Column(Float, nullable=False, default=0.0)
    # User can override allocation percentage on the fly
    custom_percentage = Column(Float, nullable=True)
    is_default = Column(Boolean(), default=False)  # True for built-in categories (Essentials, etc.)
    is_fixed = Column(Boolean(), default=False)  # True for fixed expenses, False for dynamic expenses

    created_at = Column(String, default=None)
    updated_at = Column(String, default=None)

    user = relationship("User", back_populates="categories", lazy="joined")   # see user.py
    expenses = relationship("Expense", back_populates="category", cascade="all, delete")
    transactions = relationship("Transaction", back_populates="category", cascade="all, delete")
    notifications = relationship("Notification", back_populates="category")

    def __repr__(self):
        return f"<Category name={self.name} user_id={self.user_id}>"
