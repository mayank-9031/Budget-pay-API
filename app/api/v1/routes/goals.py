# app/api/v1/routes/goals.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.goal import GoalProgressRequest, GoalProgressResponse
from app.utils.budgeting import calculate_goal_progress
from app.core.database import get_async_session
from app.core.auth import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/goals", tags=["goals"])

@router.get("/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    request: Request,
    period_request: GoalProgressRequest = Depends(),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Calculate savings goal progress based on the selected period.
    
    - **period**: The time period for calculation (daily, weekly, monthly, yearly). Default is monthly.
    
    Returns:
    - **target_amount**: Target savings amount for the selected period
    - **saved_amount**: Amount saved so far in the period
    - **progress_percentage**: Percentage of target achieved
    - **status**: Goal status (e.g., "On Track", "Behind Target")
    - **period_end_date**: End date of the current period
    - **percentage_of_income**: What percentage of income the goal represents
    - **remaining_amount**: Amount remaining to reach the target
    """
    # Calculate goal progress using the utility function
    result = await calculate_goal_progress(user, period_request.period, db)
    
    return result