# About the sanitization of this repository

This repository is a **rewritten-from-scratch reference implementation**, not an export of the
production codebase. Nothing here was copied line-for-line from the original notebooks. This was a
deliberate choice, for two reasons:

1. The original notebooks contained hardcoded company data: real partner/vendor names, internal
   Google Drive paths, Google Sheet IDs, an internal API host, SFTP account names, and — in several
   "ad-hoc fix" cells — real customer emails, phone numbers, tax IDs, and transaction IDs used to
   patch one-off bad records.
2. Jupyter notebooks persist **cell execution outputs** (printed dataframes, row counts, etc.)
   alongside the code. Even after redacting the code, previously-saved outputs could still contain
   real transaction data. Editing the original files in place could not fully rule that out — a
   clean rewrite can.

## What changed vs. the original

| Original | Here |
|---|---|
| 5 Jupyter notebooks + 1 script, each duplicating helper functions | Plain `.py` modules under `src/`, shared helpers factored into `src/common/` |
| Real company name, real e-invoicing partner name | Referred to generically as "the payment platform" and "the e-invoicing partner" throughout |
| 9+ real partner/business-line names (payment brands, a cinema chain, a resort operator, etc.) | Collapsed into 3 illustrative, fictional business lines: `wallet_fees`, `retail_topup`, `entertainment_partner` |
| Real SFTP host/username, Google Sheet IDs, service-account key path, internal API host/keys | Environment variables / OS keyring, all placeholder values in `.env.example` |
| Real customer PII (emails, phone numbers, tax IDs, addresses) in ad-hoc data-fix cells | Removed entirely; sample data in `data/sample/` is 100% synthetic |
| Real transaction/order IDs, dates, amounts | Removed; synthetic examples only |
| Internal PyPI mirror, internal SDK package name | Generic `warehouse_client.py` interface — plug in your own warehouse client |

## What was kept

The actual **engineering logic** — the parts worth showing in a portfolio — is preserved
faithfully:

- The row-limit/priority-ordering rules for splitting and uploading batches.
- The data-quality gate design (fail fast on missing/duplicate keys, wrong file counts, missing
  sheets).
- The error-classification rule engine structure (pattern → owner → action).
- The resubmission/retry-suffix logic and how refund records get repointed to the latest retry.
- The month-end reconciliation grain (date × business line × tax rate) and materiality-threshold
  flagging.

If you're comparing this against the business description on my
[portfolio page](https://sites.google.com/view/bichliennguyen/automation-projects/invoice-issuance),
this repo is the "how it's built" companion to that page's "what it achieved."
