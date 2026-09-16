"""The invoice line-item schema every business line's raw report gets mapped onto.

The real production template has ~30-38 columns to satisfy Vietnam's e-invoice XML
spec exactly (buyer bank info, payment method codes, etc.). This is a representative
subset — enough to demonstrate the mapping/validation/reconciliation techniques
without reproducing a regulatory form field-for-field.
"""
from __future__ import annotations

INVOICE_TEMPLATE_COLUMNS = [
    "invoice_no",  # blank until assigned during split_and_upload
    "invoice_date",
    "invoice_series",  # e.g. "1C26TAA" — partner/tax-authority invoice symbol
    "transaction_id",  # natural key; gets a "-R{n}" suffix on resubmission
    "original_transaction_id",  # for refunds/adjustments, points back to the original invoice
    "business_line",  # wallet_fees | retail_topup | entertainment_partner
    "buyer_name",
    "buyer_tax_id",
    "buyer_address",
    "buyer_email",
    "item_description",
    "quantity",
    "unit_price",
    "amount_excl_tax",
    "tax_rate",
    "tax_amount",
    "amount_incl_tax",
    "adjustment_type",  # None for a normal payment invoice, set for a refund/adjustment
    "source_file",
]

# Business lines used throughout the demo — fictional stand-ins for the ~9 real report
# formats in production, chosen to cover the interesting edge cases:
#   - wallet_fees: single line item per transaction, high volume
#   - retail_topup: needs buyer tax-ID resolution via a merchant mapping table
#   - entertainment_partner: multi-line-item invoices (several products per transaction)
BUSINESS_LINES = ["wallet_fees", "retail_topup", "entertainment_partner"]
MULTI_LINE_BUSINESS_LINES = {"entertainment_partner"}

ANONYMOUS_BUYER_NAME = "Người mua không lấy hóa đơn"  # "Buyer did not request invoice details"
