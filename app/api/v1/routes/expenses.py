# app/api/v1/routes/expenses.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.crud.expense import (
    create_expense_for_user,
    get_expenses_for_user,
    get_expense_by_id,
    update_expense,
    delete_expense,
)
from app.core.database import get_async_session
from app.core.auth import current_active_user, User

router = APIRouter(prefix="/expenses", tags=["expenses"])

@router.get("", response_model=List[ExpenseRead])
async def read_expenses(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await get_expenses_for_user(user.id, db)

@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense(
    ex_in: ExpenseCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await create_expense_for_user(user.id, ex_in, db)

@router.get("/{expense_id}", response_model=ExpenseRead)
async def read_expense(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return ex

@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense_endpoint(
    expense_id: uuid.UUID,
    ex_in: ExpenseUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return await update_expense(ex, ex_in, db)

@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_endpoint(
    expense_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    ex = await get_expense_by_id(expense_id, user.id, db)
    if not ex:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense not found")
    await delete_expense(ex, db)
    return None
