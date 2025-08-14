# app/crud/transaction.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, and_, func
from app.models.transaction import Transaction
from typing import Iterable, List, Optional
import uuid
from app.schemas.transaction import TransactionCreate, TransactionUpdate

async def get_transactions_for_user(user_id: uuid.UUID, db: AsyncSession) -> List[Transaction]:
    result = await db.execute(select(Transaction).where(Transaction.user_id == user_id))
    return result.scalars().all()

async def get_recent_transactions(db: AsyncSession, user_id: uuid.UUID, limit: int = 10) -> List[Transaction]:
    """Get the most recent transactions for a user with optional limit"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(desc(Transaction.transaction_date))
        .limit(limit)
    )
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


async def bulk_create_transactions_for_user(
    user_id: uuid.UUID,
    tx_inputs: Iterable[TransactionCreate],
    db: AsyncSession,
) -> List[Transaction]:
    """Efficiently inserts many transactions for a user."""
    new_instances: List[Transaction] = []
    for tx_in in tx_inputs:
        new_instances.append(Transaction(**tx_in.dict(), user_id=user_id))
    if not new_instances:
        return []
    db.add_all(new_instances)
    await db.commit()
    # refresh individually to return with IDs
    for inst in new_instances:
        await db.refresh(inst)
    return new_instances


async def transaction_exists(
    user_id: uuid.UUID,
    description: str,
    amount: float,
    transaction_date,
    db: AsyncSession,
) -> bool:
    q = select(Transaction).where(
        and_(
            Transaction.user_id == user_id,
            func.lower(Transaction.description) == func.lower(description),
            Transaction.amount == amount,
            Transaction.transaction_date == transaction_date,
        )
    )
    res = await db.execute(q)
    return res.scalar_one_or_none() is not None