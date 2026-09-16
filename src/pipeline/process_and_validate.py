"""Stage 2 — read each business line's raw report, validate it, map it onto the invoice template.

Each business line's raw export has a different shape (that's the whole reason a mapping
layer exists), but they all go through the same three steps: read -> validate -> map.
Adding a new business line means adding one `_transform_*` function and one entry in
`TRANSFORMS`; nothing else in the pipeline needs to change.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime

import pandas as pd

from src.common.io_utils import find_dated_files, str_to_float
from src.common.quality_checks import check_empty_or_duplicated_keys, check_number_of_files
from src.common.schema import INVOICE_TEMPLATE_COLUMNS

TAX_RATE = {
    "wallet_fees": 0.10,
    "retail_topup": 0.10,
    "entertainment_partner": 0.08,
}


def _base_template(n: int) -> pd.DataFrame:
    return pd.DataFrame({col: [None] * n for col in INVOICE_TEMPLATE_COLUMNS})


def _split_amount(amount_incl_tax: pd.Series, tax_rate: float) -> tuple[pd.Series, pd.Series]:
    amount_excl_tax = (amount_incl_tax / (1 + tax_rate)).round(0)
    tax_amount = amount_incl_tax - amount_excl_tax
    return amount_excl_tax, tax_amount


def transform_wallet_fees(raw: pd.DataFrame, source_file: str) -> pd.DataFrame:
    check_empty_or_duplicated_keys(
        raw, columns_must_not_be_empty=["transaction_id"], columns_must_not_be_duplicated=["transaction_id"]
    )
    out = _base_template(len(raw))
    rate = TAX_RATE["wallet_fees"]
    amount_excl, tax_amt = _split_amount(raw["fee_amount"], rate)
    out.update(
        {
            "invoice_date": raw["transaction_date"],
            "invoice_series": "1C26TAA",
            "transaction_id": raw["transaction_id"],
            "business_line": "wallet_fees",
            "buyer_name": raw.get("buyer_name"),
            "buyer_tax_id": raw.get("buyer_tax_id"),
            "item_description": "Phí dịch vụ ví điện tử - Mã GD " + raw["transaction_id"].astype(str),
            "quantity": 1,
            "unit_price": amount_excl,
            "amount_excl_tax": amount_excl,
            "tax_rate": rate,
            "tax_amount": tax_amt,
            "amount_incl_tax": raw["fee_amount"],
            "source_file": source_file,
        }
    )
    return out


def transform_retail_topup(raw: pd.DataFrame, source_file: str) -> pd.DataFrame:
    check_empty_or_duplicated_keys(
        raw, columns_must_not_be_empty=["transaction_id"], columns_must_not_be_duplicated=["transaction_id"]
    )
    out = _base_template(len(raw))
    rate = TAX_RATE["retail_topup"]
    amount_excl, tax_amt = _split_amount(raw["topup_amount"], rate)
    out.update(
        {
            "invoice_date": raw["transaction_date"],
            "invoice_series": "1C26TAB",
            "transaction_id": raw["transaction_id"],
            "business_line": "retail_topup",
            "buyer_name": raw.get("buyer_name"),
            "buyer_tax_id": raw.get("buyer_tax_id"),
            "item_description": "Hoa hồng đại lý nạp tiền - Mã GD " + raw["transaction_id"].astype(str),
            "quantity": 1,
            "unit_price": amount_excl,
            "amount_excl_tax": amount_excl,
            "tax_rate": rate,
            "tax_amount": tax_amt,
            "amount_incl_tax": raw["topup_amount"],
            "source_file": source_file,
        }
    )
    return out


def transform_entertainment_partner(raw: pd.DataFrame, source_file: str) -> pd.DataFrame:
    # Multiple line items can share a transaction_id, so the natural key for
    # duplicate-detection is the pair, not transaction_id alone.
    check_empty_or_duplicated_keys(
        raw,
        columns_must_not_be_empty=["transaction_id", "item_name"],
        columns_must_not_be_duplicated=[],
    )
    dedup_key = raw["transaction_id"].astype(str) + "|" + raw["item_name"].astype(str)
    if dedup_key.duplicated().any():
        raise ValueError("Duplicate (transaction_id, item_name) pair in entertainment_partner report")

    out = _base_template(len(raw))
    rate = TAX_RATE["entertainment_partner"]
    amount_excl, tax_amt = _split_amount(raw["item_amount"], rate)
    out.update(
        {
            "invoice_date": raw["transaction_date"],
            "invoice_series": "1C26MAA",
            "transaction_id": raw["transaction_id"],
            "business_line": "entertainment_partner",
            "buyer_name": raw.get("buyer_name"),
            "item_description": raw["item_name"],
            "quantity": raw.get("quantity", 1),
            "unit_price": amount_excl,
            "amount_excl_tax": amount_excl,
            "tax_rate": rate,
            "tax_amount": tax_amt,
            "amount_incl_tax": raw["item_amount"],
            "source_file": source_file,
        }
    )
    return out


TRANSFORMS = {
    "wallet_fees": transform_wallet_fees,
    "retail_topup": transform_retail_topup,
    "entertainment_partner": transform_entertainment_partner,
}

CURRENCY_COLUMNS = {
    "wallet_fees": ["fee_amount"],
    "retail_topup": ["topup_amount"],
    "entertainment_partner": ["item_amount"],
}


def process_business_line(business_line: str, input_dir: str, start_date: date, end_date: date) -> pd.DataFrame:
    files = find_dated_files(input_dir, prefix=f"{business_line}_", date_str="", extension=".csv")
    # Demo data ships one file per business line rather than one per day; in production
    # this calls check_number_of_files(files, start_date, end_date) against daily drops.
    if not files:
        raise FileNotFoundError(f"No input files found for business line {business_line!r} in {input_dir}")

    frames = []
    for path in files:
        raw = pd.read_csv(path, dtype={"transaction_id": str})
        raw = str_to_float(raw, CURRENCY_COLUMNS[business_line])
        frames.append(TRANSFORMS[business_line](raw, source_file=os.path.basename(path)))
    return pd.concat(frames, ignore_index=True)


def run(input_dir: str, output_dir: str, start_date: date, end_date: date) -> pd.DataFrame:
    os.makedirs(output_dir, exist_ok=True)
    all_lines = [process_business_line(bl, input_dir, start_date, end_date) for bl in TRANSFORMS]
    result = pd.concat(all_lines, ignore_index=True)
    output_path = os.path.join(output_dir, f"invoices_{start_date}_{end_date}.csv")
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), required=True)
    parser.add_argument("--end-date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), required=True)
    parser.add_argument("--input-dir", default="data/sample")
    parser.add_argument("--output-dir", default="output")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    df = run(args.input_dir, args.output_dir, args.start_date, args.end_date)
    print(f"Processed {len(df)} invoice line(s) across {df['business_line'].nunique()} business line(s).")
