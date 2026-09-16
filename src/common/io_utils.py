"""File-reading helpers shared across pipeline stages.

These were originally re-implemented with small variations in three different notebooks.
Factoring them out here is one of the few structural changes vs. the original: same
behavior, one definition.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Iterable

import pandas as pd

CURRENCY_CHARS = re.compile(r"[,\s₫₫\-]")


def skip_header(df: pd.DataFrame, keyword_start: str) -> int:
    """Find how many leading rows to skip before the real header.

    Many partner report exports have title/metadata rows above the actual column
    header. Returns the 0-based row index where a cell equals `keyword_start`.
    """
    for idx, row in df.iterrows():
        if keyword_start in row.astype(str).values:
            return idx
    raise ValueError(f"Could not locate header row starting with {keyword_start!r}")


def get_latest_file(paths: Iterable[str]) -> str:
    """Return the most recently modified file among `paths`."""
    paths = list(paths)
    if not paths:
        raise FileNotFoundError("No candidate files provided")
    return max(paths, key=os.path.getmtime)


def str_to_float(df: pd.DataFrame, string_cols: Iterable[str]) -> pd.DataFrame:
    """Strip currency formatting (thousands separators, currency symbol, dashes) and cast to float."""
    df = df.copy()
    for col in string_cols:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(CURRENCY_CHARS, "", regex=True)
            .replace("", "0")
            .astype(float)
        )
    return df


def safe_read_excel_sheet(
    path: str,
    sheet_name: str,
    empty_columns: list[str],
    dtype: dict | None = None,
) -> pd.DataFrame:
    """Read a named sheet, tolerating a missing sheet by returning an empty typed frame.

    Report formats occasionally drop a sheet entirely for a given date (e.g. no refunds
    that day). Downstream code should not have to special-case that.
    """
    try:
        return pd.read_excel(path, sheet_name=sheet_name, dtype=dtype)
    except ValueError:
        return pd.DataFrame(columns=empty_columns)


def check_sheet_exists(path: str, expected_sheets: Iterable[str]) -> list[str]:
    """Return any expected sheet names missing from the workbook at `path`."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    actual = set(wb.sheetnames)
    return [s for s in expected_sheets if s not in actual]


def find_dated_files(directory: str, prefix: str, date_str: str, extension: str = ".csv") -> list[str]:
    """List files in `directory` whose name starts with `prefix` + `date_str`."""
    pattern = os.path.join(directory, f"{prefix}{date_str}*{extension}")
    return sorted(glob.glob(pattern, recursive=False))
