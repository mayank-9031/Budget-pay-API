# app/crud/goal.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.goal import Goal
from typing import List, Optional
import uuid
from app.schemas.goal import GoalCreate, GoalUpdate

async def get_goals_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Goal]:
    result = await db.execute(select(Goal).where(Goal.user_id == user_id))
    return result.scalars().all()

async def get_goal_by_id(goal_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Optional[Goal]:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_goal_for_user(user_id: uuid.UUID, goal_in: GoalCreate, db: AsyncSession) -> Goal:
    new_goal = Goal(**goal_in.dict(), user_id=user_id)
    db.add(new_goal)
    await db.commit()
    await db.refresh(new_goal)
    return new_goal

async def update_goal(goal: Goal, goal_in: GoalUpdate, db: AsyncSession) -> Goal:
    for field, value in goal_in.dict(exclude_unset=True).items():
        setattr(goal, field, value)
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal

async def delete_goal(goal: Goal, db: AsyncSession) -> None:
    await db.delete(goal)
    await db.commit()
