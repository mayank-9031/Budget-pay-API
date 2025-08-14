# app/utils/transactions_import.py
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
from datetime import datetime
import csv
import io
from enum import Enum

import pandas as pd
import pdfplumber


def _normalize(s: str) -> str:
    return s.strip().lower().replace("\ufeff", "") if isinstance(s, str) else s


def _find_column(header: List[str], candidates: Iterable[str]) -> Optional[int]:
    normalized = [_normalize(h) for h in header]
    for idx, name in enumerate(normalized):
        for cand in candidates:
            if cand == name:
                return idx
    # allow contains match
    for idx, name in enumerate(normalized):
        for cand in candidates:
            if cand in name:
                return idx
    return None


def _parse_float(value: str) -> Optional[float]:
    if value is None:
        return None
    s = _normalize(str(value))
    if s in ("", "-"):
        return None
    # remove thousand separators and currency symbols
    s = s.replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    # try common bank statement formats
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return datetime(dt.year, dt.month, dt.day)  # zero time
        except ValueError:
            continue
    # fallback: try ISO parse
    try:
        dt = datetime.fromisoformat(s)
        return datetime(dt.year, dt.month, dt.day)
    except Exception:
        return None


def parse_bank_statement_csv(file_bytes: bytes) -> List[Dict[str, Optional[str]]]:
    """
    Returns a list of rows with canonical keys: date, description, debit, credit, ref
    Only parses the file; does not filter debit/credit.
    """
    text = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = rows[0]
    data_rows = rows[1:]

    date_idx = _find_column(header, [
        "date", "transaction date", "txn date", "value date", "value dt", "valuedt", "posting date",
    ])
    desc_idx = _find_column(header, [
        "description", "narration", "details", "merchant", "remarks", "particulars",
    ])
    debit_idx = _find_column(header, [
        "debit", "debit amount", "withdrawal amt.", "withdrawal amount", "withdrawal", "dr",
    ])
    credit_idx = _find_column(header, [
        "credit", "credit amount", "deposit amt.", "deposit amount", "deposit", "cr",
    ])
    amount_idx = _find_column(header, [
        "amount", "transaction amount", "amt",
    ])
    type_idx = _find_column(header, [
        "type", "transaction type", "dr/cr", "dr/ cr", "debit/credit", "crdr",
    ])
    ref_idx = _find_column(header, [
        "ref", "ref no", "reference", "reference no", "utr", "transaction id", "cheque no",
    ])

    normalized_rows: List[Dict[str, Optional[str]]] = []
    for raw in data_rows:
        # skip empty lines
        if not any(cell.strip() for cell in raw if isinstance(cell, str)):
            continue
        date_val = raw[date_idx] if date_idx is not None and date_idx < len(raw) else None
        desc_val = raw[desc_idx] if desc_idx is not None and desc_idx < len(raw) else None
        debit_val = raw[debit_idx] if debit_idx is not None and debit_idx < len(raw) else None
        credit_val = raw[credit_idx] if credit_idx is not None and credit_idx < len(raw) else None
        amount_val = raw[amount_idx] if amount_idx is not None and amount_idx < len(raw) else None
        type_val = raw[type_idx] if type_idx is not None and type_idx < len(raw) else None
        ref_val = raw[ref_idx] if ref_idx is not None and ref_idx < len(raw) else None

        normalized_rows.append({
            "date": date_val,
            "description": desc_val,
            "debit": debit_val,
            "credit": credit_val,
            "amount": amount_val,
            "type": type_val,
            "ref": ref_val,
        })

    return normalized_rows


def parse_bank_statement_excel(file_bytes: bytes) -> List[Dict[str, Optional[str]]]:
    """Parse .xlsx or .xls into our normalized row dicts."""
    buf = io.BytesIO(file_bytes)
    
    # Try to determine file type and use appropriate engine
    try:
        # First, try reading with openpyxl (for .xlsx files)
        df = pd.read_excel(buf, engine="openpyxl")
    except Exception as e:
        # If that fails, try with xlrd (for .xls files)
        buf.seek(0)  # Reset buffer position
        try:
            df = pd.read_excel(buf, engine="xlrd")
        except Exception:
            # If both fail, try without specifying engine (pandas will auto-detect)
            buf.seek(0)
            df = pd.read_excel(buf)
    
    if df.empty:
        return []
    
    header = [str(c) for c in df.columns]
    date_idx = _find_column(header, ["date", "transaction date", "txn date", "value date", "value dt", "valuedt", "posting date"]) or 0
    desc_idx = _find_column(header, ["description", "narration", "details", "merchant", "remarks", "particulars"]) or 1
    debit_idx = _find_column(header, ["debit", "debit amount", "withdrawal amt.", "withdrawal amount", "withdrawal", "dr"]) 
    credit_idx = _find_column(header, ["credit", "credit amount", "deposit amt.", "deposit amount", "deposit", "cr"]) 
    amount_idx = _find_column(header, ["amount", "transaction amount", "amt"]) 
    type_idx = _find_column(header, ["type", "transaction type", "dr/cr", "dr/ cr", "debit/credit", "crdr"]) 
    ref_idx = _find_column(header, ["ref", "ref no", "reference", "reference no", "utr", "transaction id", "cheque no"]) 

    normalized_rows: List[Dict[str, Optional[str]]] = []
    for _, row in df.iterrows():
        def val(idx: Optional[int]) -> Optional[str]:
            if idx is None:
                return None
            try:
                v = row.iloc[idx]
            except Exception:
                return None
            if pd.isna(v):
                return None
            return str(v)

        normalized_rows.append({
            "date": val(date_idx),
            "description": val(desc_idx),
            "debit": val(debit_idx),
            "credit": val(credit_idx),
            "amount": val(amount_idx),
            "type": val(type_idx),
            "ref": val(ref_idx),
        })
    return normalized_rows


def parse_bank_statement_pdf(file_bytes: bytes) -> List[Dict[str, Optional[str]]]:
    """
    Parse bank statement PDFs by extracting tables. Best-effort; supports HDFC-like layouts.
    """
    normalized_rows: List[Dict[str, Optional[str]]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables or []:
                if not table:
                    continue
                header = [str(h) if h is not None else "" for h in table[0]]
                # Attempt to detect familiar HDFC headers with stars/lines removed
                header = [_normalize(h).replace("*", "").replace(".", "").strip() for h in header]
                # Find indices
                date_idx = _find_column(header, ["date", "valuedt", "value dt", "valuedate"]) 
                desc_idx = _find_column(header, ["narration", "description", "details"]) 
                ref_idx = _find_column(header, ["chqrefno", "chq/refno", "ref", "ref no", "utr"]) 
                debit_idx = _find_column(header, ["withdrawalamt", "withdrawal amt", "debit", "dr"]) 
                credit_idx = _find_column(header, ["depositamt", "deposit amt", "credit", "cr"]) 

                # Fallback to positional mapping for known HDFC layout when header match fails
                if debit_idx is None and len(header) >= 6:
                    # Typical order: Date, Narration, Chq./Ref.No., Value Dt, Withdrawal Amt., Deposit Amt., Closing Balance
                    date_idx = 0 if date_idx is None else date_idx
                    desc_idx = 1 if desc_idx is None else desc_idx
                    # Some PDFs might omit Chq/Ref column; guard with bounds
                    ref_idx = 2 if (ref_idx is None and len(header) >= 3) else ref_idx
                    # Value Dt at 3 (ignored)
                    debit_idx = 4 if debit_idx is None and len(header) >= 5 else debit_idx
                    credit_idx = 5 if credit_idx is None and len(header) >= 6 else credit_idx

                for raw in table[1:]:
                    # Skip decorative rows
                    if not any(str(c or "").strip() for c in raw):
                        continue
                    get = lambda idx: (raw[idx] if idx is not None and idx < len(raw) else None)
                    row = {
                        "date": get(date_idx),
                        "description": get(desc_idx),
                        "debit": get(debit_idx),
                        "credit": get(credit_idx),
                        "amount": None,
                        "type": None,
                        "ref": get(ref_idx),
                    }
                    # Some HDFC PDFs bunch entire columns into a single multi-line cell.
                    # If so, explode them into individual rows using heuristics.
                    if any(isinstance(row.get(k), str) and "\n" in str(row.get(k)) for k in ["date", "description", "debit", "credit"]):
                        normalized_rows.extend(_explode_multiline_pdf_row(row))
                    else:
                        normalized_rows.append(row)
    return normalized_rows


def _explode_multiline_pdf_row(row: Dict[str, Optional[str]]) -> List[Dict[str, Optional[str]]]:
    """Explode a PDF table row where each cell contains multiple newline-separated values."""
    
    def split_lines(val: Optional[str]) -> List[str]:
        if not isinstance(val, str) or not val.strip():
            return []
        lines = [l.strip() for l in val.split("\n") if l.strip()]
        return lines

    dates = split_lines(row.get("date"))
    debits = split_lines(row.get("debit"))  
    credits = split_lines(row.get("credit"))
    desc_lines = split_lines(row.get("description"))
    refs = split_lines(row.get("ref"))

    # For HDFC statements, the pattern is usually:
    # - Each transaction has a date
    # - Description might span multiple lines per transaction
    # - Debit OR credit amount (not both) per transaction
    
    # The key insight: use dates as the primary driver since each transaction has a date
    if not dates:
        return []
    
    num_transactions = len(dates)
    
    # Process descriptions - group them by transaction
    # For HDFC, every 2 description lines typically belong to one transaction
    desc_groups = []
    if desc_lines:
        # Group description lines (typically 2 lines per transaction for HDFC)
        lines_per_transaction = len(desc_lines) // num_transactions if num_transactions > 0 else 1
        lines_per_transaction = max(1, lines_per_transaction)  # At least 1 line per transaction
        
        for i in range(0, len(desc_lines), lines_per_transaction):
            group_lines = desc_lines[i:i + lines_per_transaction]
            desc_groups.append(" ".join(group_lines))
    
    # Pad descriptions if we have fewer than transactions
    while len(desc_groups) < num_transactions:
        desc_groups.append("")

    result = []
    debit_idx = 0
    credit_idx = 0
    
    for i in range(num_transactions):
        date_val = dates[i] if i < len(dates) else None
        desc_val = desc_groups[i] if i < len(desc_groups) else None
        ref_val = refs[i] if i < len(refs) else None
        
        # Determine if this transaction is debit or credit based on description
        # and assign the next available amount
        debit_val = None
        credit_val = None
        
        if desc_val:
            # For HDFC statements, look for patterns that indicate debit vs credit
            desc_upper = desc_val.upper()
            if any(keyword in desc_upper for keyword in ['UPI-', 'POS ', 'ATM', 'WITHDRAWAL']):
                # This looks like a debit transaction
                if debit_idx < len(debits):
                    debit_val = debits[debit_idx]
                    debit_idx += 1
            else:
                # This might be a credit transaction
                if credit_idx < len(credits):
                    credit_val = credits[credit_idx]
                    credit_idx += 1
        
        # If we still don't have an amount, try to assign whatever is available
        if debit_val is None and credit_val is None:
            if debit_idx < len(debits):
                debit_val = debits[debit_idx]
                debit_idx += 1
            elif credit_idx < len(credits):
                credit_val = credits[credit_idx]
                credit_idx += 1
        
        result.append({
            "date": date_val,
            "description": desc_val,
            "debit": debit_val,
            "credit": credit_val,
            "amount": None,
            "type": None,
            "ref": ref_val,
        })
    
    return result



def compute_withdrawal_amount(row: Dict[str, Optional[str]]) -> Optional[float]:
    """
    Determine the outgoing (debit) amount from a normalized row.
    Returns positive float for withdrawals; None if not a withdrawal.
    """
    debit = _parse_float(row.get("debit"))
    credit = _parse_float(row.get("credit"))
    amount = _parse_float(row.get("amount"))
    tx_type = _normalize(row.get("type")) if row.get("type") is not None else None

    if debit is not None and debit > 0:
        return debit
    if credit is not None and credit > 0:
        return None

    if amount is not None:
        # Prefer explicit type if present
        if tx_type in ("debit", "dr", "d"):
            return abs(amount)
        if tx_type in ("credit", "cr", "c"):
            return None
        # No type; infer by sign only. Positive => treat as credit (skip); Negative => debit
        if amount < 0:
            return abs(amount)
        return None

    return None


def build_description(row: Dict[str, Optional[str]]) -> str:
    base = (row.get("description") or "").strip()
    ref = (row.get("ref") or "").strip()
    if ref:
        return f"{base} (Ref: {ref})" if base else f"Ref: {ref}"
    return base or "Transaction"


KeywordMap = Dict[str, str]


DEFAULT_KEYWORD_TO_CATEGORY: KeywordMap = {
    # Food and dining
    "zomato": "Food & Dining",
    "swiggy": "Food & Dining",
    "restaurant": "Food & Dining",
    "cafe": "Food & Dining",
    "coffee": "Food & Dining",
    "food": "Food & Dining",
    "grocery": "Groceries",
    "supermarket": "Groceries",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "petrol": "Transport",
    "diesel": "Transport",
    "fuel": "Transport",
    "ola": "Transport",
    "uber": "Transport",
    "metro": "Transport",
    "bus": "Transport",
    "train": "Travel",
    "irctc": "Travel",
    "air": "Travel",
    "airasia": "Travel",
    "indigo": "Travel",
    "spicejet": "Travel",
    "hotel": "Travel",
    "rent": "Rent",
    "electricity": "Utilities",
    "water": "Utilities",
    "internet": "Utilities",
    "broadband": "Utilities",
    "mobile": "Utilities",
    "prepaid": "Utilities",
    "postpaid": "Utilities",
    "dth": "Utilities",
    "insurance": "Insurance",
    "lic": "Insurance",
    "health": "Healthcare",
    "hospital": "Healthcare",
    "pharmacy": "Healthcare",
    "medical": "Healthcare",
    "doctor": "Healthcare",
    "pharmeasy": "Healthcare",
    "1mg": "Healthcare",
    "upi": "Transfers",
    "imps": "Transfers",
    "neft": "Transfers",
    "rtgs": "Transfers",
    "atm": "Cash Withdrawal",
    "cash": "Cash Withdrawal",
}


def choose_category_name_from_keywords(description: str, user_category_names: List[str]) -> Optional[str]:
    text = _normalize(description or "")
    if not text:
        return None

    # Check explicit keyword mapping
    for keyword, cat_name in DEFAULT_KEYWORD_TO_CATEGORY.items():
        if keyword in text:
            return cat_name

    # Fallback: if any of user's existing category names appear in description
    for name in user_category_names:
        if name and _normalize(name) in text:
            return name

    return None



