"""Stage 4 — pull the partner's processing results and classify every non-success outcome.

Downloads the partner's result files for a batch date, tallies counts by status, and
runs every failed row through a small "whose fault, what action" rule engine. The
classified summary is upserted into a tracking spreadsheet keyed by (batch_date,
business_line) — the same sheet is later used to compute the service fee owed between
the two parties, so it has to be idempotent under re-runs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import pandas as pd

from config import CONFIG
from src.common.sftp_client import connect, download_files
from src.common.sheets_client import open_worksheet, upsert_by_key

SUCCESS_STATUS = "S"


@dataclass
class ErrorRule:
    owner: str
    action: str
    matches: Callable[[pd.Series], pd.Series]  # vectorized predicate over the result frame


ERROR_RULES: list[ErrorRule] = [
    ErrorRule(
        owner="tax_authority",
        action="Follow up with the e-invoice partner on whether the tax code was actually issued",
        matches=lambda df: df["message"].str.contains("timeout|not found after receiving code", case=False, na=False),
    ),
    ErrorRule(
        owner="einvoice_partner",
        action="Re-upload after fixing the partner-side config issue",
        matches=lambda df: df["message"].str.contains(
            "duplicate|invalid sign time", case=False, na=False
        ),
    ),
    ErrorRule(
        owner="pending",
        action="Wait for the next sync; result not yet available",
        matches=lambda df: df["message"].isna() | (df["message"].str.strip() == ""),
    ),
]


def classify(results: pd.DataFrame) -> pd.DataFrame:
    """Add `owner` and `action` columns to every result row based on status/message."""
    results = results.copy()
    results["owner"] = None
    results["action"] = None

    is_success = results["status"] == SUCCESS_STATUS
    results.loc[is_success, "owner"] = "none"

    remaining = ~is_success
    for rule in ERROR_RULES:
        apply_to = remaining & rule.matches(results)
        results.loc[apply_to, ["owner", "action"]] = [rule.owner, rule.action]
        remaining &= ~apply_to

    results.loc[remaining, ["owner", "action"]] = ["unclassified", "Needs manual review"]
    return results


def summarize(classified: pd.DataFrame, batch_date: date) -> pd.DataFrame:
    summary = (
        classified.groupby(["business_line", "status", "owner", "action"], dropna=False)
        .agg(transaction_count=("transaction_id", "nunique"), amount_incl_tax=("amount_incl_tax", "sum"))
        .reset_index()
    )
    summary.insert(0, "batch_date", batch_date.isoformat())
    return summary


def sync_batch(batch_date: date) -> pd.DataFrame:
    date_str = batch_date.strftime("%Y%m%d")
    with connect(CONFIG.sftp) as sftp:
        result_paths = download_files(
            sftp,
            CONFIG.sftp.remote_incoming_dir,
            CONFIG.paths.result_dir,
            prefix="RESULT",
            date_str=date_str,
        )

    if not result_paths:
        results = pd.DataFrame(columns=["transaction_id", "business_line", "status", "message", "amount_incl_tax"])
    else:
        results = pd.concat((pd.read_csv(p, dtype={"transaction_id": str}) for p in result_paths), ignore_index=True)

    classified = classify(results)
    summary = summarize(classified, batch_date)

    worksheet = open_worksheet(CONFIG.sheets, CONFIG.sheets.daily_report_sheet_id, "Daily report")
    upsert_by_key(worksheet, summary, key_columns=["batch_date", "business_line"])
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=date.today())
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = sync_batch(args.batch_date)
    print(summary.to_string(index=False))
