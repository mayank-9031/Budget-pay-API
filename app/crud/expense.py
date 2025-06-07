# app/crud/expense.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.expense import Expense
from typing import List, Optional
import uuid
from app.schemas.expense import ExpenseCreate, ExpenseUpdate

async def get_expenses_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Expense]:
    result = await db.execute(select(Expense).where(Expense.user_id == user_id))
    return result.scalars().all()

async def get_expense_by_id(expense_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Optional[Expense]:
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_expense_for_user(user_id: uuid.UUID, ex_in: ExpenseCreate, db: AsyncSession) -> Expense:
    new_ex = Expense(**ex_in.dict(), user_id=user_id)
    db.add(new_ex)
    await db.commit()
    await db.refresh(new_ex)
    return new_ex

async def update_expense(expense: Expense, ex_in: ExpenseUpdate, db: AsyncSession) -> Expense:
    for field, value in ex_in.dict(exclude_unset=True).items():
        setattr(expense, field, value)
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return expense

async def delete_expense(expense: Expense, db: AsyncSession) -> None:
    await db.delete(expense)
    await db.commit()
