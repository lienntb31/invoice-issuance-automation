"""Thin wrapper around gspread for idempotent tracking-sheet writes.

The pattern used throughout the pipeline is "delete-then-append by key": read the whole
sheet, drop any existing rows that match the new batch's key columns, append the new
rows, and rewrite the sheet. Re-running a sync for the same batch is therefore safe.
"""
from __future__ import annotations

from typing import Iterable

import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe

from config import SheetsConfig


def open_worksheet(cfg: SheetsConfig, sheet_id: str, worksheet_name: str) -> gspread.Worksheet:
    gc = gspread.service_account(filename=cfg.service_account_path)
    return gc.open_by_key(sheet_id).worksheet(worksheet_name)


def read_as_dataframe(worksheet: gspread.Worksheet) -> pd.DataFrame:
    values = worksheet.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame()
    return pd.DataFrame(values[1:], columns=values[0])


def upsert_by_key(
    worksheet: gspread.Worksheet,
    new_rows: pd.DataFrame,
    key_columns: Iterable[str],
) -> pd.DataFrame:
    """Replace any existing rows sharing `key_columns` with `new_rows`, then write back the union."""
    key_columns = list(key_columns)
    existing = read_as_dataframe(worksheet)

    if not existing.empty:
        new_keys = new_rows[key_columns].drop_duplicates()
        merge_indicator = existing.merge(new_keys, on=key_columns, how="left", indicator=True)
        existing = existing.loc[merge_indicator["_merge"].values == "left_only"]

    combined = pd.concat([existing, new_rows], ignore_index=True)
    worksheet.clear()
    set_with_dataframe(worksheet, combined)
    return combined
