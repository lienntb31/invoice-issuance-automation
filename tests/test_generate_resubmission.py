import pandas as pd

from src.pipeline.generate_resubmission import (
    latest_retry_lookup,
    next_retry_id,
    repoint_refunds,
    split_retry_suffix,
)


def test_split_retry_suffix_on_original_transaction():
    assert split_retry_suffix("T1") == ("T1", 0)


def test_split_retry_suffix_on_retried_transaction():
    assert split_retry_suffix("T1-R02") == ("T1", 2)


def test_next_retry_id_increments():
    assert next_retry_id("T1") == "T1-R01"
    assert next_retry_id("T1-R01") == "T1-R02"


def test_latest_retry_lookup_keeps_highest_retry_per_base():
    resubmitted = pd.DataFrame({"transaction_id": ["T1-R01", "T1-R02", "T2-R01"]})

    lookup = latest_retry_lookup(resubmitted)

    lookup = lookup.set_index("base_transaction_id")["latest_transaction_id"]
    assert lookup["T1"] == "T1-R02"
    assert lookup["T2"] == "T2-R01"


def test_repoint_refunds_uses_latest_retry_id():
    refunds = pd.DataFrame({"transaction_id": ["RF1"], "original_transaction_id": ["T1"]})
    retry_lookup = pd.DataFrame({"base_transaction_id": ["T1"], "latest_transaction_id": ["T1-R02"]})

    repointed = repoint_refunds(refunds, retry_lookup)

    assert repointed.loc[0, "original_transaction_id"] == "T1-R02"


def test_repoint_refunds_leaves_unresubmitted_original_id_untouched():
    refunds = pd.DataFrame({"transaction_id": ["RF1"], "original_transaction_id": ["T9"]})
    retry_lookup = pd.DataFrame({"base_transaction_id": ["T1"], "latest_transaction_id": ["T1-R02"]})

    repointed = repoint_refunds(refunds, retry_lookup)

    assert repointed.loc[0, "original_transaction_id"] == "T9"
