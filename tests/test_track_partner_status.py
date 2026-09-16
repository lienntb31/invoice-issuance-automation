import pandas as pd

from src.pipeline.track_partner_status import classify


def _results(rows):
    return pd.DataFrame(rows, columns=["transaction_id", "status", "message"])


def test_success_rows_get_no_owner():
    results = _results([("T1", "S", None)])

    classified = classify(results)

    assert classified.loc[0, "owner"] == "none"


def test_timeout_message_classified_as_tax_authority():
    results = _results([("T1", "F", "Cassandra timeout while issuing code")])

    classified = classify(results)

    assert classified.loc[0, "owner"] == "tax_authority"


def test_duplicate_message_classified_as_partner_actionable():
    results = _results([("T1", "F", "duplicate invoice serial and number")])

    classified = classify(results)

    assert classified.loc[0, "owner"] == "einvoice_partner"
    assert "re-upload" in classified.loc[0, "action"].lower()


def test_blank_message_classified_as_pending():
    results = _results([("T1", "F", None), ("T2", "F", "")])

    classified = classify(results)

    assert list(classified["owner"]) == ["pending", "pending"]


def test_unrecognized_message_falls_back_to_unclassified():
    results = _results([("T1", "F", "some brand-new error we've never seen")])

    classified = classify(results)

    assert classified.loc[0, "owner"] == "unclassified"
