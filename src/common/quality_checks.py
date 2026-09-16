"""Fail-fast data-quality gates.

Philosophy: a wrong invoice is worse than a delayed invoice. Every gate here raises
rather than warns, so a bad upstream file blocks the run instead of silently producing
incorrect tax documents.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd


class DataQualityError(Exception):
    """Raised when an upstream file fails a validation gate."""


def check_number_of_files(paths: list[str], start_date: date, end_date: date) -> None:
    """Assert we found exactly one file per calendar day in [start_date, end_date]."""
    expected = (end_date - start_date).days + 1
    if len(paths) != expected:
        raise DataQualityError(
            f"Expected {expected} file(s) for {start_date}..{end_date}, found {len(paths)}: {paths}"
        )


def check_empty_or_duplicated_keys(
    df: pd.DataFrame,
    columns_must_not_be_empty: Iterable[str],
    columns_must_not_be_duplicated: Iterable[str],
) -> None:
    """Assert natural-key columns have no blanks and no duplicate values.

    This is the primary gate before mapping a source report onto the invoice template —
    a blank or duplicated transaction key downstream becomes a missing or double invoice.
    """
    for col in columns_must_not_be_empty:
        empty_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        if empty_mask.any():
            raise DataQualityError(
                f"Column {col!r} has {empty_mask.sum()} empty value(s):\n{df.loc[empty_mask].head()}"
            )

    for col in columns_must_not_be_duplicated:
        dup_mask = df[col].duplicated(keep=False)
        if dup_mask.any():
            raise DataQualityError(
                f"Column {col!r} has {dup_mask.sum()} duplicated value(s):\n{df.loc[dup_mask].head()}"
            )


def previous_business_day(reference: date) -> date:
    """Return the previous business day (Monday -> last Friday, otherwise -> yesterday)."""
    if reference.weekday() == 0:  # Monday
        return reference - timedelta(days=3)
    return reference - timedelta(days=1)
