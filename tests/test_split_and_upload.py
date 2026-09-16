import pandas as pd

from src.pipeline.split_and_upload import (
    PRIORITY_SERIES,
    build_upload_plan,
    chunk_preserving_groups,
    order_for_upload,
)


def _row(transaction_id, invoice_series, adjustment_type, invoice_date):
    return {
        "transaction_id": transaction_id,
        "invoice_series": invoice_series,
        "adjustment_type": adjustment_type,
        "invoice_date": invoice_date,
    }


def test_priority_series_uploaded_before_normal_series():
    priority_series = next(iter(PRIORITY_SERIES))
    df = pd.DataFrame(
        [
            _row("T1", "OTHER", None, "2026-01-02"),
            _row("T2", priority_series, None, "2026-01-03"),
            _row("T3", "OTHER", None, "2026-01-01"),
        ]
    )

    ordered = order_for_upload(df)

    assert ordered.iloc[0]["transaction_id"] == "T2"


def test_payment_uploaded_before_refund_within_same_priority_tier():
    df = pd.DataFrame(
        [
            _row("T1", "OTHER", "REFUND", "2026-01-01"),
            _row("T2", "OTHER", None, "2026-01-02"),
        ]
    )

    ordered = order_for_upload(df)

    assert list(ordered["transaction_id"]) == ["T2", "T1"]


def test_ordered_within_tier_by_date():
    df = pd.DataFrame(
        [
            _row("T1", "OTHER", None, "2026-01-05"),
            _row("T2", "OTHER", None, "2026-01-01"),
            _row("T3", "OTHER", None, "2026-01-03"),
        ]
    )

    ordered = order_for_upload(df)

    assert list(ordered["transaction_id"]) == ["T2", "T3", "T1"]


def test_chunk_preserving_groups_never_splits_a_transaction():
    df = pd.DataFrame(
        {
            "transaction_id": ["T1", "T1", "T2", "T3"],
            "value": [1, 2, 3, 4],
        }
    )

    chunks = chunk_preserving_groups(df, group_col="transaction_id", max_rows=2)

    for chunk in chunks:
        assert len(chunk) <= 2
    # T1's two rows must land in the same chunk
    t1_chunk_sizes = [len(c[c["transaction_id"] == "T1"]) for c in chunks]
    assert 2 in t1_chunk_sizes


def test_build_upload_plan_respects_max_rows_and_assigns_sequential_invoice_numbers():
    df = pd.DataFrame(
        [_row(f"T{i}", "OTHER", None, "2026-01-01") for i in range(5)]
    )

    plan = build_upload_plan(df, max_rows=2)

    assert sum(len(chunk) for chunk in plan) == 5
    assert all(len(chunk) <= 2 for chunk in plan)
    for chunk in plan:
        assert list(chunk["invoice_no"]) == list(range(1, len(chunk) + 1))
