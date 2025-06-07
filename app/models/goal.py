# app/models/goal.py
import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Goal(Base):
    __tablename__ = "goals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_amount = Column(Float, nullable=False)
    deadline = Column(DateTime, nullable=False)
    # Track how much is saved so far, updated by service logic
    saved_amount = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=None)
    updated_at = Column(DateTime, default=None)

    user = relationship("User", back_populates="goals", lazy="joined")

    def __repr__(self):
        return f"<Goal target={self.target_amount} deadline={self.deadline} user_id={self.user_id}>"
