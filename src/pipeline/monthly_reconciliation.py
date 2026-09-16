"""Stage 6 — month-end reconciliation between issued invoices and revenue booking.

Runs once a month across the accumulated daily output. Rather than matching at the
individual-transaction level (which would require both sides to share a perfectly
consistent key, and they don't — booking records get corrected/backdated), this
aggregates both sides independently to the grain of (date, business_line, tax_rate)
and diffs the aggregates. Any cell where the two sides disagree by more than a
materiality threshold is a real "invoiced too much / too little" gap worth
investigating, broken down by business line for cost-center reporting.
"""
from __future__ import annotations

import pandas as pd

GRAIN = ["invoice_date", "business_line", "tax_rate"]


def summarize_invoiced(invoices: pd.DataFrame) -> pd.DataFrame:
    return (
        invoices.groupby(GRAIN, dropna=False)
        .agg(amount_incl_tax=("amount_incl_tax", "sum"), tax_amount=("tax_amount", "sum"))
        .reset_index()
    )


def summarize_booking(booking: pd.DataFrame) -> pd.DataFrame:
    """Booking records don't carry a `tax_amount` column — it's derived the same way as stage 2."""
    summary = (
        booking.groupby(GRAIN[:2], dropna=False)["gross_amount"].sum().reset_index()
    )
    summary = summary.merge(booking[["business_line", "tax_rate"]].drop_duplicates(), on="business_line")
    summary["amount_incl_tax"] = summary["gross_amount"]
    summary["tax_amount"] = (summary["gross_amount"] * summary["tax_rate"] / (1 + summary["tax_rate"])).round(0)
    return summary[GRAIN + ["amount_incl_tax", "tax_amount"]]


def reconcile(invoiced: pd.DataFrame, booked: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    merged = invoiced.merge(
        booked, on=GRAIN, how="outer", suffixes=("_invoiced", "_booked")
    ).fillna(0)

    merged["diff_amount_incl_tax"] = merged["amount_incl_tax_invoiced"] - merged["amount_incl_tax_booked"]
    merged["diff_tax_amount"] = merged["tax_amount_invoiced"] - merged["tax_amount_booked"]

    flagged = merged[merged["diff_amount_incl_tax"].abs() > tolerance].copy()
    flagged["direction"] = flagged["diff_amount_incl_tax"].apply(
        lambda d: "over-invoiced" if d > 0 else "under-invoiced"
    )
    return flagged.sort_values(by=["business_line", "invoice_date"])


def run(invoices: pd.DataFrame, booking: pd.DataFrame, tolerance: float = 1.0) -> pd.DataFrame:
    invoiced_summary = summarize_invoiced(invoices)
    booked_summary = summarize_booking(booking)
    return reconcile(invoiced_summary, booked_summary, tolerance)
