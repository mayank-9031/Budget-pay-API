# app/crud/transaction.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.transaction import Transaction
from typing import List, Optional
import uuid
from app.schemas.transaction import TransactionCreate, TransactionUpdate

async def get_transactions_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Transaction]:
    result = await db.execute(select(Transaction).where(Transaction.user_id == user_id))
    return result.scalars().all()

async def get_transaction_by_id(transaction_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_transaction_for_user(user_id: uuid.UUID, tx_in: TransactionCreate, db: AsyncSession) -> Transaction:
    new_tx = Transaction(**tx_in.dict(), user_id=user_id)
    db.add(new_tx)
    await db.commit()
    await db.refresh(new_tx)
    return new_tx

async def update_transaction(tx: Transaction, tx_in: TransactionUpdate, db: AsyncSession) -> Transaction:
    for field, value in tx_in.dict(exclude_unset=True).items():
        setattr(tx, field, value)
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx

async def delete_transaction(tx: Transaction, db: AsyncSession) -> None:
    await db.delete(tx)
    await db.commit()
