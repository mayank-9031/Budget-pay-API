# app/api/v1/routes/transactions.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from app.crud.transaction import (
    create_transaction_for_user,
    get_transactions_for_user,
    get_transaction_by_id,
    update_transaction,
    delete_transaction,
)
from app.core.database import get_async_session
from app.core.auth import current_active_user, User

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.get("", response_model=List[TransactionRead])
async def read_transactions(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    return await get_transactions_for_user(user.id, db)

@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    tx_in: TransactionCreate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    # Optionally: auto-categorize if category_id is None (use keywords)
    return await create_transaction_for_user(user.id, tx_in, db)

@router.get("/{transaction_id}", response_model=TransactionRead)
async def read_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    tx = await get_transaction_by_id(transaction_id, user.id, db)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx

@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction_endpoint(
    transaction_id: uuid.UUID,
    tx_in: TransactionUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    tx = await get_transaction_by_id(transaction_id, user.id, db)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return await update_transaction(tx, tx_in, db)

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    tx = await get_transaction_by_id(transaction_id, user.id, db)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    await delete_transaction(tx, db)
    return None
