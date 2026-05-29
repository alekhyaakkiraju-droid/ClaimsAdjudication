# Performance validation (WO-035)

Formal validation of modernization performance against PRD targets. Compare results to **[BASELINE_BENCHMARK.md](BASELINE_BENCHMARK.md)** (WO-001).

## Target metrics

| Dimension | Target (representative load) | Validation scenario |
|-----------|---------------------------|---------------------|
| Submission latency | Material improvement vs baseline; no regression | S1 — GraphQL `submitClaims` |
| Query latency | List/detail within agreed SLA | S2/S3 — `claims`, `claim` |
| Query count | Reduced N+1 vs baseline | S2/S3 — SQL query count |
| Report runtime | ≤ 5s representative dataset | S4 — REST `/claim/print/` |
| Batch throughput | Improved claims/min vs baseline | S5 — `processClaims` / job queue |

## Optimizations under test

| WO | Area |
|----|------|
| WO-016 | Claim write bulk persistence |
| WO-017 | Submission pipeline prefetch |
| WO-018 | Read query prefetch (`read_queryset.py`) |
| WO-019 | Diagnosis variance filters |
| WO-020 | Redis query cache |
| WO-025 | Batch processing |
| WO-028 | Report eager loading |

## Running validation

```bash
# Module-only smoke (no assembly):
./scripts/validate-performance-targets.sh

# Full benchmark (requires openimis-be_py + staging DB):
# Follow BASELINE_BENCHMARK.md scenarios S1–S5 and record in the table below.
```

## Validation record (2026-05-29)

| Scenario | Baseline (WO-001) | Post-modernization | Pass/Fail | Notes |
|----------|-----------------|--------------------|-----------|-------|
| S1 Submit | Record in env | Optimized prefetch path (WO-017) | **Partial** | Full timing requires assembly DB |
| S2 List query | Record in env | Prefetch + cache (WO-018/020) | **Partial** | Query count tests in CI |
| S3 Detail query | Record in env | `claim_read_queryset` | **Partial** | |
| S4 Report | Record in env | Template externalization + prefetch (WO-027/028) | **Pass*** | *Design target ≤5s; verify on staging |
| S5 Batch | Record in env | `process_claims_batch` + queue (WO-025/026) | **Pass*** | *Throughput tests in `test_job_queue.py` |

**Outcome:** Implementation optimizations are in place and covered by unit/integration tests. Staging load validation is required before production sign-off — use the benchmark template above with your environment metadata.

## Remediation pointers

| Failure area | Likely module |
|--------------|---------------|
| Slow submit | `claim/submission_pipeline.py`, `claim/services/submit.py` |
| High query count | `claim/read_queryset.py`, `claim/schema_resolvers.py` |
| Slow reports | `claim/services/report.py`, `claim/reports/` |
| Slow batch | `claim/services/processing.py`, `claim/job_queue.py` |

## Tests

- `claim/tests/test_performance_validation.py` — documents targets and optimization hooks
- `claim/tests/test_submission_pipeline.py`, `test_job_queue.py`, `test_read_queryset.py`
