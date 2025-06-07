# app/models/transaction.py
import uuid
from sqlalchemy import Column, String, ForeignKey, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(length=255), nullable=False)
    amount = Column(Float, nullable=False)
    category_id = Column(PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    transaction_date = Column(DateTime, nullable=False)

    created_at = Column(DateTime, default=None)
    updated_at = Column(DateTime, default=None)

    user = relationship("User", back_populates="transactions", lazy="joined")
    category = relationship("Category", back_populates="transactions", lazy="joined")

    def __repr__(self):
        return f"<Transaction amount={self.amount} date={self.transaction_date} user_id={self.user_id}>"
