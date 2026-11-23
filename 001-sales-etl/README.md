# Day 001 — Trustworthy sales ETL

Learn extraction, validation, transformation, loading, and SQL aggregation with Python's standard library. No accounts, services, or dependencies are required. The included data is synthetic.

## Run

From this directory with Python 3.10 or newer:

```sh
python3 pipeline.py
python3 -m unittest -v
```

The first run inserts three orders, skips one exact duplicate, and rejects three invalid/conflicting rows. Revenue is 1,350 cents for Coffee and 900 cents for Tea. Running again inserts nothing and keeps totals unchanged.

## Design

CSV → row validation → SQLite transaction → product revenue report

Invalid rows → `rejects.json` with source line, reason, and original values.

The primary key is order ID. Exact repeated records are skipped; conflicting records are rejected rather than silently overwriting data. Prices use Decimal during parsing and integer cents in storage. The database persists between runs; the rejection report describes the latest run. An invalid CSV header aborts loading. Infrastructure/file errors fail the process instead of being reported as bad rows.

## Learn by changing it

Add a daily revenue report using GROUP BY order_date. Add a new order, rerun, and verify only that order is inserted. Then change an existing order's quantity and examine the rejection report. Explain why this pipeline needs a deliberate update policy before it could handle refunds or corrected orders.

## Scope

A small single-process learning pipeline. It is not a full order-management system: one order ID represents one product line. Reject output and the database are separate files, so their writes are not atomic together. Large workloads need bounded rejection output, aggregate-overflow handling, operational logging, and a stronger recovery strategy.
