"""Stage 3 — split the day's invoices into partner-sized files and upload over SFTP.

The partner enforces two constraints that drive all the logic here:
  1. No file may exceed MAX_ROWS_PER_FILE rows.
  2. Files must arrive in a specific priority order: certain invoice series must be
     processed before the rest of the day's batch, and within any priority tier,
     payment invoices must be processed before refund/adjustment invoices, ordered
     by invoice date.

A secondary constraint — multi-line invoices (e.g. entertainment_partner, where one
transaction has several item rows) must never be split across two files, since the
partner assembles one invoice per transaction_id per file.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime

import pandas as pd

from config import CONFIG
from src.common.sftp_client import connect, upload_files

# Invoice series that must reach the partner ahead of the rest of the day's batch.
# In production this reflects a partner-side processing-queue constraint; here it's
# illustrated with the "coded" wallet_fees series taking priority over the others.
PRIORITY_SERIES = {"1C26TAA"}


def _priority_rank(series: pd.Series) -> pd.Series:
    return (~series.isin(PRIORITY_SERIES)).astype(int)  # 0 = priority, 1 = normal


def _payment_rank(adjustment_type: pd.Series) -> pd.Series:
    return adjustment_type.notna().astype(int)  # 0 = payment, 1 = refund/adjustment


def order_for_upload(df: pd.DataFrame) -> pd.DataFrame:
    """Sort rows into the required upload order: priority > payment-before-refund > date."""
    ordered = df.assign(
        _priority_rank=_priority_rank(df["invoice_series"]),
        _payment_rank=_payment_rank(df["adjustment_type"]),
    ).sort_values(by=["_priority_rank", "_payment_rank", "invoice_date"])
    return ordered.drop(columns=["_priority_rank", "_payment_rank"])


def chunk_preserving_groups(df: pd.DataFrame, group_col: str, max_rows: int) -> list[pd.DataFrame]:
    """Split `df` into chunks of at most `max_rows` rows, without splitting any `group_col` group.

    Row order is preserved. Groups are assumed already contiguous (i.e. `df` was sorted
    such that all rows for a given transaction_id are adjacent).
    """
    chunks: list[list[pd.DataFrame]] = [[]]
    current_size = 0

    for _, group in df.groupby(group_col, sort=False):
        if current_size + len(group) > max_rows and current_size > 0:
            chunks.append([])
            current_size = 0
        chunks[-1].append(group)
        current_size += len(group)

    return [pd.concat(chunk, ignore_index=True) for chunk in chunks if chunk]


def assign_invoice_numbers(chunk: pd.DataFrame) -> pd.DataFrame:
    """Assign a contiguous 1..N invoice number sequence within a single output file."""
    chunk = chunk.copy()
    invoice_no_by_transaction = {
        txn_id: i + 1 for i, txn_id in enumerate(chunk["transaction_id"].drop_duplicates())
    }
    chunk["invoice_no"] = chunk["transaction_id"].map(invoice_no_by_transaction)
    return chunk


def build_upload_plan(df: pd.DataFrame, max_rows: int) -> list[pd.DataFrame]:
    ordered = order_for_upload(df)
    chunks = chunk_preserving_groups(ordered, group_col="transaction_id", max_rows=max_rows)
    return [assign_invoice_numbers(chunk) for chunk in chunks]


def export_chunks(chunks: list[pd.DataFrame], output_dir: str, batch_date: date, prefix: str = "INV") -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    date_str = batch_date.strftime("%Y%m%d")
    paths = []
    for idx, chunk in enumerate(chunks, start=1):
        filename = f"{prefix}{date_str}{idx:03d}.csv"
        path = os.path.join(output_dir, filename)
        chunk.to_csv(path, index=False, encoding="utf-8-sig")
        paths.append(path)
    return paths


def upload_batch(local_paths: list[str]) -> list[str]:
    with connect(CONFIG.sftp) as sftp:
        return upload_files(sftp, local_paths, CONFIG.sftp.remote_outgoing_dir, overwrite=False)


def _describe_plan(chunks: list[pd.DataFrame]) -> None:
    for idx, chunk in enumerate(chunks, start=1):
        priority_count = chunk["invoice_series"].isin(PRIORITY_SERIES).sum()
        refund_count = chunk["adjustment_type"].notna().sum()
        print(
            f"file {idx}: {len(chunk)} row(s), {priority_count} priority-series, "
            f"{refund_count} refund/adjustment, dates {chunk['invoice_date'].min()}..{chunk['invoice_date'].max()}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", default=None, help="Invoice CSV from stage 2; defaults to today's output")
    parser.add_argument("--batch-date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=date.today())
    parser.add_argument("--dry-run", action="store_true", help="Print the planned file split/order, don't upload")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    input_csv = args.input_csv or os.path.join(
        CONFIG.paths.output_dir, f"invoices_{args.batch_date}_{args.batch_date}.csv"
    )
    invoices = pd.read_csv(input_csv, dtype={"transaction_id": str})
    plan = build_upload_plan(invoices, max_rows=CONFIG.rules.max_rows_per_file)

    if args.dry_run:
        _describe_plan(plan)
    else:
        local_paths = export_chunks(plan, CONFIG.paths.upload_dir, args.batch_date)
        uploaded = upload_batch(local_paths)
        print(f"Uploaded {len(uploaded)} of {len(local_paths)} file(s).")
