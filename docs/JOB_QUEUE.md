# WO-026: Database-backed job queue

## Overview

Long-running claim operations (large `process_claims` batches, future report
generation) can be enqueued in the `claim_ClaimJob` table and processed by a
worker instead of blocking GraphQL request threads.

## Configuration (`ClaimConfig`)

| Key | Default | Purpose |
|-----|---------|---------|
| `job_queue_enabled` | `true` | Master switch for queue infrastructure |
| `job_queue_async_threshold` | `0` | Minimum claim count to auto-enqueue (`0` = always sync, backward compatible) |
| `job_queue_max_retries` | `3` | Retries before marking a job failed |
| `job_queue_name` | `default` | Queue name polled by the worker |

## Worker

Run on-premises alongside the openIMIS backend:

```bash
python manage.py process_claim_jobs
```

Options: `--once` (single job), `--sleep SECONDS`, `--rate-limit SECONDS`, optional queue name argument.

## GraphQL

- **`claimJob(uuid: String!)`** — job status, result, and errors (requires process-claims permission)
- **`claimJobs`** — list/filter jobs (newest first)

When a batch is enqueued, `processClaims` returns no claim-level errors; poll `claimJob` (or filter `claimJobs` by `clientMutationId`) for completion.

## Job types

| Type | Handler |
|------|---------|
| `process_claims` | Uses WO-025 `process_claims_batch` |
| `generate_report` | Reserved hook for WO-027/WO-028 |

## Verification

- `claim/tests/test_job_queue.py`
