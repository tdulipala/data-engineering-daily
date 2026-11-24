# Day 002 — Resumable API ingestion

An interrupted API download should resume from its last committed page. This beginner project adds pagination, bounded HTTP retries, persistent checkpoints, and atomic page loading to yesterday's deduplication concepts.

## Run locally

Python 3.10+; standard library only. From this directory:

```sh
python3 pipeline.py
python3 pipeline.py
python3 -m unittest -v
```

The default demo reads the bundled synthetic JSON API responses without network access. The first run commits two pages and stores three unique events: books = 2 events / 2,000 cents; games = 1 event / 2,500 cents. The second run commits zero pages and returns the same totals. Use a fresh database filename to start over.

## Exercise the HTTP client

In one terminal, from this directory:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory fixtures
```

In another:

```sh
python3 pipeline.py --base-url http://127.0.0.1:8000 --database http-demo.db
```

Stop the server with Ctrl+C when finished. The included server serves static fixtures, not a third-party API. The client expects page1.json, page2.json, etc., each containing an items array and next_page integer or null. Adapt this contract when integrating a real provider.

## Architecture and failure behavior

```text
JSON page → validate pagination → SQLite transaction → category totals
                                  ├─ insert unique events
                                  └─ save next-page checkpoint
```

Each page commits its events and checkpoint together. A network failure leaves earlier committed pages intact. Invalid rows or conflicting event IDs roll back the whole current page, including its checkpoint. Exact duplicates are harmless. Completion is stored as a null next_page, so completed snapshots are not fetched again. The database is bound to a source identifier to prevent accidental reuse for a different snapshot.

HTTP GET requests retry timeouts, transport errors, HTTP 429, and selected 5xx responses, with at most three attempts and 0.5/1-second backoff. Other HTTP errors fail immediately. Malformed JSON is not retried. A ten-second timeout applies to each request.

## Validation

Six automated tests cover resume after failure, completed-run behavior, page rollback, conflicting duplicates, cursor loops, source binding, retry success, retry exhaustion, and nonretryable HTTP errors. The HTTP transport is mocked in tests; the offline CLI demo is separately exercised. The localhost command above is available for manual HTTP integration testing.

## Learning exercise

Remove page2.json temporarily, run against a fresh database, restore the file, and rerun. Inspect the checkpoint with SQLite and explain why page 1 does not need another download. Then introduce a conflicting event on page 2 and observe that the cursor does not advance.

## Scope and tradeoffs

This handles a finite, immutable snapshot with consecutive page numbers and one writer per database. It does not implement incremental polling, changing source snapshots, deletion propagation, opaque cursors, authentication, Retry-After parsing, jitter, streaming response-size limits, or concurrent workers. Use a new database for a new snapshot. Aggregated integer totals assume small demo volumes. Keep credentials out of source URLs. The synthetic fixtures can be freely reused.
