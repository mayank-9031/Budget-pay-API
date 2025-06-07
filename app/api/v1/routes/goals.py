# app/api/v1/routes/goals.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.schemas.goal import GoalCreate, GoalRead, GoalUpdate
from app.crud.goal import (
    create_goal_for_user,
    get_goals_for_user,
    get_goal_by_id,
    update_goal,
    delete_goal,
)
from app.core.database import get_async_session
from app.core.auth import current_active_user, User

router = APIRouter(prefix="/goals", tags=["goals"])

@router.get("", response_model=List[GoalRead])
async def read_goals(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await get_goals_for_user(user.id, db)

@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    goal_in: GoalCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await create_goal_for_user(user.id, goal_in, db)

@router.get("/{goal_id}", response_model=GoalRead)
async def read_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    goal = await get_goal_by_id(goal_id, user.id, db)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal

@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal_endpoint(
    goal_id: uuid.UUID,
    goal_in: GoalUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    goal = await get_goal_by_id(goal_id, user.id, db)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return await update_goal(goal, goal_in, db)

@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal_endpoint(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    goal = await get_goal_by_id(goal_id, user.id, db)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    await delete_goal(goal, db)
    return None
