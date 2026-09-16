# Automated Tax Invoice Issuance & Reconciliation Pipeline

A reference implementation of a production pipeline I built and operate at a large Vietnamese fintech
company to comply with Vietnam's real-time e-invoicing mandate (effective March 2025). It turns
raw transaction data spread across an internal data warehouse and several partner report formats
into tax-compliant e-invoices, submits them to a certified e-invoicing partner connected to the
national tax authority system, and reconciles the results — daily and at month-end.

> **Note on this repository.** This is a **sanitized, from-scratch reference implementation** of the
> real pipeline, rewritten to demonstrate the engineering techniques without exposing any company
> data, partner names, credentials, or real transactions. All company/partner names below are
> generic placeholders, all sample data is synthetic, and all secrets are read from environment
> variables / the OS credential store — never hardcoded. See [`SANITIZATION.md`](SANITIZATION.md)
> for exactly what was changed and why.
>
> A narrative write-up of the original project (business context, impact) is on my
> [portfolio site](https://sites.google.com/view/bichliennguyen/automation-projects/invoice-issuance).

## Why this exists

Vietnam's Tax Authority requires real-time e-invoicing for every in-scope transaction, with
significant penalties for non-compliance. At the scale of hundreds of thousands of daily
transactions across multiple products, that's not something a human can do by hand — it needs
a pipeline that is:

- **Correct** — every transaction gets exactly one invoice, in the right format, with valid
  buyer tax information.
- **Fast** — invoices must reach the tax authority in near real time, batched into the partner's
  technical constraints.
- **Auditable** — every batch's outcome (success, partner error, tax-authority error) must be
  tracked, explainable, and tied to a cost-sharing/service-fee record between the two parties.
- **Self-healing** — failed transactions must be automatically detected and re-submitted without
  manual triage of every error.

## Pipeline overview

```
 1. Extract            2. Process &            3. Split &              4. Track partner
    from warehouse         validate                upload                  processing
 ┌────────────────┐    ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
 │ Pull raw         │   │ Standardize into│   │ Chunk to        │   │ Pull result     │
 │ transactions from│──▶│ the invoice     │──▶│ ≤20,000 rows,   │──▶│ files, tally    │
 │ the warehouse &  │   │ template; run   │   │ order by        │   │ status, classify│
 │ partner report   │   │ data-quality    │   │ priority; push  │   │ errors, log to  │
 │ exports          │   │ gates           │   │ via SFTP        │   │ a tracking sheet│
 └────────────────┘    └────────────────┘    └────────────────┘    └───────┬────────┘
                                                                            │
                              ┌─────────────────────────────────────────────┘
                              ▼
                     5. Generate resubmission        6. Month-end reconciliation
                    ┌────────────────────┐         ┌──────────────────────────┐
                    │ Auto-build a        │         │ Compare invoiced totals   │
                    │ "make-up" batch for │────────▶│ vs. revenue booking by    │
                    │ every failed        │ (repeat │ date × business line ×   │
                    │ transaction         │  daily) │ tax rate; flag gaps      │
                    └────────────────────┘         └──────────────────────────┘
```

Steps 1–5 run once per business day; step 6 runs once per month across the accumulated daily
output.

### 1. Extract from the warehouse ([`src/pipeline/extract_from_warehouse.py`](src/pipeline/extract_from_warehouse.py))
Pulls raw transaction data for a date range from the internal data warehouse via a paginated,
schema-typed query client ([`src/common/warehouse_client.py`](src/common/warehouse_client.py)), and
cross-references a buyer/tax-ID mapping sheet to resolve which transactions can carry full buyer
information vs. an anonymous "retail buyer" invoice (per tax compliance rules for low-value/anonymous
transactions).

### 2. Process & validate ([`src/pipeline/process_and_validate.py`](src/pipeline/process_and_validate.py))
Reads heterogeneous report exports (Excel/CSV, one format per business line), standardizes them
into a single invoice line-item schema, and runs fail-fast **data-quality gates** before anything
is allowed downstream:
- expected file count for the date range,
- no missing/duplicated natural keys,
- expected worksheet names present.

### 3. Split & upload ([`src/pipeline/split_and_upload.py`](src/pipeline/split_and_upload.py))
The e-invoicing partner enforces a hard technical limit of **20,000 rows per file** and expects
files to arrive in a specific order:
1. Certain invoice types must be pushed **before** the rest of the batch (a partner-side processing
   constraint),
2. within that, **payment** invoices before **refund/adjustment** invoices,
3. within that, ordered by invoice date.

The splitter groups multi-line invoices so a single invoice's line items are never separated across
files, assigns a contiguous invoice-number sequence per output file, and uploads over SFTP with a
resumable/idempotent overwrite check (skip vs. replace an already-uploaded file).

### 4. Track partner processing status ([`src/pipeline/track_partner_status.py`](src/pipeline/track_partner_status.py))
Downloads the partner's result files for each uploaded batch, computes counts by status, and runs
error messages through a **rule engine** that classifies each failure by "whose fault, what action":

| Failure pattern | Classification | Action |
|---|---|---|
| Tax-authority system timeout / desync | Tax authority | Follow up with the e-invoice partner |
| Partner-side misconfiguration (duplicate serial, invalid sign time, etc.) | E-invoice partner | Re-upload |
| Result still pending | Pending | Wait for next sync |
| Success | — | — |
| Anything else | Unclassified | Manual review |

Results are upserted into a tracking spreadsheet (matched and replaced by date+batch key, so
re-running a sync is idempotent), which is later used as the basis for the service-fee calculation
between the two parties.

### 5. Generate resubmission batch ([`src/pipeline/generate_resubmission.py`](src/pipeline/generate_resubmission.py))
For every transaction classified as an actionable partner-side failure, automatically builds a new
invoice record for the next batch: clears the old invoice number, rolls the invoice date forward,
and appends an incrementing `-R{n}` retry suffix to the transaction key (so the Nth retry is always
traceable back to the original transaction). Refund records that reference a resubmitted original
invoice are automatically repointed to the latest retry ID.

### 6. Month-end reconciliation ([`src/pipeline/monthly_reconciliation.py`](src/pipeline/monthly_reconciliation.py))
Aggregates invoiced amounts (from step 2's output) and revenue-booking source records independently
by **(date, business line, tax rate)**, outer-joins the two aggregates on that key, and flags any
cell where the difference exceeds a materiality threshold — surfacing over-invoiced or
under-invoiced business lines for a specific day, without needing transaction-level matching.

## Shared building blocks ([`src/common/`](src/common/))

The original notebooks reimplemented the same handful of helpers in three separate places. This
version factors them out once:

- `io_utils.py` — locate the real header row in a report with leading title rows, pick the
  latest file by mtime, safely read a workbook sheet that might not exist, coerce
  currency-formatted strings to floats.
- `quality_checks.py` — the fail-fast validation gates described in step 2.
- `sftp_client.py` — thin wrapper around Paramiko for listing/uploading/downloading with an
  overwrite policy.
- `sheets_client.py` — thin wrapper around gspread for idempotent "delete matching rows, then
  append" upserts into a tracking spreadsheet.
- `warehouse_client.py` — a generic paginated, schema-typed query client interface (swap in your
  own warehouse SDK/driver).

## Configuration

All connection details are supplied via environment variables (see [`.env.example`](.env.example))
or the OS keyring for passwords — nothing is hardcoded. See [`config.py`](config.py).

## Running the demo

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your own values, or leave as-is to run against sample data
python -m src.pipeline.process_and_validate --start-date 2026-01-01 --end-date 2026-01-01 \
    --input-dir data/sample --output-dir output
python -m src.pipeline.split_and_upload --dry-run  # prints the planned split/upload order
```

`data/sample/` contains small, entirely synthetic CSV files (fabricated names, IDs, and amounts)
so the pipeline is runnable end-to-end without any real data.

## Tech stack

Python, pandas, paramiko (SFTP), gspread (Google Sheets), pytest.

## Tests

```bash
pytest tests/
```

Covers the chunking/priority-ordering logic (step 3) and the error-classification rule engine
(step 4), since those are the two places where a subtle bug silently produces wrong invoices.
