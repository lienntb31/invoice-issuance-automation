"""Stage 5 — auto-build tomorrow's "make-up" batch for today's actionable failures.

Every transaction classified as an `einvoice_partner`-owned failure (see
track_partner_status.py) needs to be resubmitted: same line-item data, cleared invoice
number, invoice date rolled forward to the next business day, and the transaction_id
gets an incrementing `-R{n}` suffix so the Nth retry is always traceable back to the
original transaction. Any refund/adjustment invoice that references a resubmitted
original invoice must be repointed to that invoice's latest retry ID — otherwise the
refund would reference a transaction_id the partner already rejected.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from src.common.quality_checks import previous_business_day

RETRY_SUFFIX = re.compile(r"^(?P<base>.+)-R(?P<n>\d+)$")


def split_retry_suffix(transaction_id: str) -> tuple[str, int]:
    """Return (base_transaction_id, retry_number). retry_number is 0 for an original transaction."""
    match = RETRY_SUFFIX.match(transaction_id)
    if not match:
        return transaction_id, 0
    return match.group("base"), int(match.group("n"))


def next_retry_id(transaction_id: str) -> str:
    base, n = split_retry_suffix(transaction_id)
    return f"{base}-R{n + 1:02d}"


def build_resubmission_batch(failed_transaction_ids: pd.Series, original_invoices: pd.DataFrame, today: date) -> pd.DataFrame:
    """Build resubmission rows for every failed transaction_id, sourcing line data from `original_invoices`."""
    to_resubmit = original_invoices[original_invoices["transaction_id"].isin(failed_transaction_ids)].copy()
    to_resubmit["invoice_no"] = None
    to_resubmit["invoice_date"] = previous_business_day(today).isoformat()
    to_resubmit["transaction_id"] = to_resubmit["transaction_id"].map(next_retry_id)
    return to_resubmit


def latest_retry_lookup(resubmitted: pd.DataFrame) -> pd.DataFrame:
    """For every base transaction_id, keep only the highest-numbered retry.

    Returns columns [base_transaction_id, latest_transaction_id] — used to repoint
    refund rows that still reference an older, superseded retry.
    """
    parsed = resubmitted["transaction_id"].map(split_retry_suffix)
    resubmitted = resubmitted.assign(
        base_transaction_id=[p[0] for p in parsed],
        retry_number=[p[1] for p in parsed],
    )
    latest_idx = resubmitted.groupby("base_transaction_id")["retry_number"].idxmax()
    latest = resubmitted.loc[latest_idx, ["base_transaction_id", "transaction_id"]]
    return latest.rename(columns={"transaction_id": "latest_transaction_id"})


def repoint_refunds(refunds: pd.DataFrame, retry_lookup: pd.DataFrame) -> pd.DataFrame:
    """Replace `original_transaction_id` on refund rows with the latest retry ID, where one exists."""
    merged = refunds.merge(
        retry_lookup, left_on="original_transaction_id", right_on="base_transaction_id", how="left"
    )
    merged["original_transaction_id"] = merged["latest_transaction_id"].fillna(merged["original_transaction_id"])
    return merged.drop(columns=["base_transaction_id", "latest_transaction_id"])


def split_payment_vs_refund(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_refund = df["adjustment_type"].notna()
    return df.loc[~is_refund].copy(), df.loc[is_refund].copy()
