"""Stage 1 — pull raw transactions from the warehouse and resolve buyer tax info.

Two things happen here that only make sense together:
1. Raw transactions are pulled per business line for the date range, paginated
   through WarehouseClient (see src/common/warehouse_client.py).
2. Each transaction is cross-referenced against a buyer/tax-ID mapping (itself sourced
   from a merchant onboarding sheet + a "tax-ID not yet verified" tracking sheet) to
   decide whether it can carry full buyer info on the invoice, or must fall back to an
   anonymous "retail buyer" invoice — a real compliance rule for low-value/anonymous
   transactions under Vietnam's e-invoicing regulation.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from config import CONFIG
from src.common.schema import ANONYMOUS_BUYER_NAME
from src.common.sheets_client import open_worksheet, read_as_dataframe
from src.common.warehouse_client import QuerySpec, WarehouseClient


def load_buyer_tax_mapping() -> pd.DataFrame:
    """Combine the merchant-onboarding mapping with the unverified-tax-ID exclusion list.

    Returns columns: [account_id, buyer_name, buyer_tax_id, buyer_address, buyer_email].
    Rows whose tax ID appears in the "not yet verified" sheet have buyer_tax_id blanked out,
    forcing them to the anonymous-buyer path downstream.
    """
    worksheet = open_worksheet(
        CONFIG.sheets, CONFIG.sheets.tax_id_tracker_sheet_id, "unverified_tax_ids"
    )
    unverified = read_as_dataframe(worksheet)
    unverified_ids = set(unverified.get("national_id", pd.Series(dtype=str)).astype(str).str.zfill(12))

    # In production this also merges two Excel "merchant registry" exports (chain-store
    # and non-chain-store) with the sheet above. Omitted here since it's pure I/O glue;
    # the interesting part is the exclusion-list join below.
    mapping = pd.DataFrame(
        columns=["account_id", "buyer_name", "buyer_tax_id", "buyer_address", "buyer_email"]
    )
    mapping.loc[mapping["buyer_tax_id"].isin(unverified_ids), "buyer_tax_id"] = None
    return mapping


def resolve_buyer_info(transactions: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Left-join transactions to the buyer mapping; fall back to an anonymous buyer when unresolved."""
    merged = transactions.merge(mapping, on="account_id", how="left")
    unresolved = merged["buyer_tax_id"].isna()
    merged.loc[unresolved, "buyer_name"] = ANONYMOUS_BUYER_NAME
    merged.loc[unresolved, ["buyer_tax_id", "buyer_address", "buyer_email"]] = None
    return merged


def extract(business_line: str, start_date: date, end_date: date) -> pd.DataFrame:
    client = WarehouseClient(CONFIG.warehouse)
    spec = QuerySpec(api_name=f"invoicing__{business_line}", start_date=start_date, end_date=end_date)
    transactions = client.query_all(spec)
    mapping = load_buyer_tax_mapping()
    return resolve_buyer_info(transactions, mapping)
