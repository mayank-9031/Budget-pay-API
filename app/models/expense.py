# app/models/expense.py
import uuid
from sqlalchemy import Column, String, ForeignKey, Float, Boolean, Enum, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class FrequencyType(str, enum.Enum):
    one_time = "one_time"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    custom = "custom"  # e.g. every 10 days, every 15 days

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(length=150), nullable=False)
    amount = Column(Float, nullable=False)
    category_id = Column(PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Is this expense recurring?
    frequency_type = Column(Enum(FrequencyType), default=FrequencyType.one_time, nullable=False)
    # If frequency_type == custom, this is the integer for “every X days”
    interval_days = Column(Integer, nullable=True)
    next_due_date = Column(DateTime, nullable=True)
    # For “skipping” or “pausing” recurring bills
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=None)
    updated_at = Column(DateTime, default=None)

    user = relationship("User", back_populates="expenses", lazy="joined")        # see user.py
    category = relationship("Category", back_populates="expenses", lazy="joined")    # see category.py

    def __repr__(self):
        return f"<Expense name={self.name} amount={self.amount} user_id={self.user_id}>"
