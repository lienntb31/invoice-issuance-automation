"""Generic paginated, schema-typed data warehouse client.

The original pipeline queries an internal, pre-registered-query API in front of the
warehouse (rather than raw SQL), which enforces a max-rows-per-call cap and returns
everything as strings alongside a column-type schema. This module reproduces that
*shape* generically — swap `WarehouseClient._fetch_page` for your own driver
(BigQuery, Snowflake, Presto/Trino, a REST gateway, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

import pandas as pd

from config import WarehouseConfig

SQL_TO_PANDAS_DTYPE = {
    "varchar": "string",
    "date": "datetime64[ns]",
    "decimal": "float64",
    "double": "float64",
    "bigint": "int64",
}


@dataclass
class QuerySpec:
    api_name: str
    start_date: date
    end_date: date
    chunk_size: int = 50_000


class WarehouseClient:
    def __init__(self, cfg: WarehouseConfig):
        self._cfg = cfg

    def count(self, spec: QuerySpec) -> int:
        """Return the total row count for `spec` (used to size the pagination loop)."""
        raise NotImplementedError("Plug in your own warehouse driver here.")

    def _fetch_page(self, spec: QuerySpec, start_id: int) -> tuple[pd.DataFrame, dict[str, str]]:
        """Fetch one page starting at `start_id`, returning (rows, column->sql_type schema)."""
        raise NotImplementedError("Plug in your own warehouse driver here.")

    def query_all(self, spec: QuerySpec) -> pd.DataFrame:
        """Paginate through every shard for `spec` and return one typed, concatenated DataFrame."""
        total_rows = self.count(spec)
        frames: list[pd.DataFrame] = []
        start_id = 0
        while start_id < total_rows:
            page, schema = self._fetch_page(spec, start_id)
            if page.empty:
                break
            frames.append(_apply_schema(page, schema))
            start_id += spec.chunk_size

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)


def _apply_schema(df: pd.DataFrame, schema: dict[str, str]) -> pd.DataFrame:
    """Cast string columns returned by the API into their declared SQL types."""
    df = df.copy()
    for column, sql_type in schema.items():
        if column not in df.columns:
            continue
        pandas_dtype = SQL_TO_PANDAS_DTYPE.get(sql_type.lower())
        if pandas_dtype is None:
            continue
        df[column] = df[column].astype(pandas_dtype, errors="ignore")
    return df
