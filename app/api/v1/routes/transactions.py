# app/api/v1/routes/transactions.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid

from app.schemas.transaction import (
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
    TransactionImportResult,
)
from app.crud.transaction import (
    create_transaction_for_user,
    get_transactions_for_user,
    get_transaction_by_id,
    update_transaction,
    delete_transaction,
    bulk_create_transactions_for_user,
    transaction_exists,
)
from app.core.database import get_async_session
from app.core.auth import User
from app.api.deps import get_current_user
from app.crud.category import get_categories_for_user, get_category_by_name_for_user, create_category_for_user
from app.schemas.category import CategoryCreate
from app.utils.transactions_import import (
    parse_bank_statement_csv,
    parse_bank_statement_excel,
    parse_bank_statement_pdf,
    compute_withdrawal_amount,
    build_description,
    choose_category_name_from_keywords,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.get("", response_model=List[TransactionRead])
async def read_transactions(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    return await get_transactions_for_user(user_id, db)

@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    tx_in: TransactionCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    # Optionally: auto-categorize if category_id is None (use keywords)
    return await create_transaction_for_user(user_id, tx_in, db)

@router.get("/{transaction_id}", response_model=TransactionRead)
async def read_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    tx = await get_transaction_by_id(transaction_id, user_id, db)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx

@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction_endpoint(
    transaction_id: uuid.UUID,
    tx_in: TransactionUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    tx = await get_transaction_by_id(transaction_id, user_id, db)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return await update_transaction(tx, tx_in, db)

@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    transaction_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    # Convert user.id to UUID
    user_id = uuid.UUID(str(user.id))
    tx = await get_transaction_by_id(transaction_id, user_id, db)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    await delete_transaction(tx, db)
    return None


@router.post("/import", response_model=TransactionImportResult)
async def import_transactions_from_statement(
    request: Request,
    file: UploadFile = File(...),
    create_missing_categories: bool = Form(True),
    skip_duplicates: bool = Form(True),
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Import transactions from a CSV bank statement. Only withdrawal amounts are recorded.
    Tries to auto-categorize via narration/keywords. Optionally creates categories if missing.
    """
    user_id = uuid.UUID(str(user.id))

    if (file.content_type or "").lower() not in ("text/csv", "application/vnd.ms-excel", "application/csv"):
        # Allow anyway; we will try to parse as CSV regardless of content-type
        pass

    content = await file.read()
    filename = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()
    rows = []
    try:
        if filename.endswith(".csv") or "csv" in ctype:
            rows = parse_bank_statement_csv(content)
        elif filename.endswith(".xlsx") or filename.endswith(".xls") or "excel" in ctype:
            rows = parse_bank_statement_excel(content)
        elif filename.endswith(".pdf") or "pdf" in ctype:
            rows = parse_bank_statement_pdf(content)
        else:
            # try csv as fallback
            rows = parse_bank_statement_csv(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
    if not rows:
        return TransactionImportResult(created_count=0, skipped_count=0, created=[], skipped_reasons=["No data rows found"]) 

    user_categories = await get_categories_for_user(user_id, db)
    user_category_names = [c.name for c in user_categories]

    tx_inputs: List[TransactionCreate] = []
    skipped_reasons: List[str] = []

    for r in rows:
        amount = compute_withdrawal_amount(r)
        if amount is None or amount <= 0:
            # enrich reason for debugging
            debug_raw = {
                "date": r.get("date"),
                "desc": r.get("description"),
                "debit": r.get("debit"),
                "credit": r.get("credit"),
                "amount": r.get("amount"),
                "type": r.get("type"),
            }
            print(debug_raw)
            skipped_reasons.append("Not a withdrawal or amount missing")
            continue
        dt = None
        if r.get("date"):
            from app.utils.transactions_import import _parse_date  # local import to reuse
            dt = _parse_date(r["date"])  # type: ignore
        if dt is None:
            skipped_reasons.append("Invalid date")
            continue

        description = build_description(r)

        # Determine category
        chosen_name: Optional[str] = choose_category_name_from_keywords(description, user_category_names)
        category_id: Optional[uuid.UUID] = None
        if chosen_name:
            existing = await get_category_by_name_for_user(chosen_name, user_id, db)
            if existing is None and create_missing_categories:
                new_cat = await create_category_for_user(user_id, CategoryCreate(name=chosen_name, description=None, default_percentage=0.0, custom_percentage=None, is_default=False, is_fixed=False), db)
                user_category_names.append(new_cat.name)
                category_id = new_cat.id
            elif existing is not None:
                category_id = existing.id

        if skip_duplicates:
            if await transaction_exists(user_id, description, amount, dt, db):
                skipped_reasons.append("Duplicate transaction")
                continue
        tx_inputs.append(TransactionCreate(description=description, amount=amount, category_id=category_id, transaction_date=dt))

    created = await bulk_create_transactions_for_user(user_id, tx_inputs, db)

    created_read = [TransactionRead.model_validate(c, from_attributes=True) for c in created]
    return TransactionImportResult(
        created_count=len(created),
        skipped_count=len(skipped_reasons),
        created=created_read,
        skipped_reasons=skipped_reasons,
    )
