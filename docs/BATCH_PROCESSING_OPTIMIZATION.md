# Batch claim processing optimization (WO-025)

## Change

`claim/batch_processing.py` centralizes eager loading and batch helpers for `process_claims`:

- `claim_process_queryset()` — extends submission prefetches with diagnosis relations
- `load_claims_for_processing()` — single query batch load preserving caller UUID order
- `BatchPolicyCache` — preloads policies per `(insuree_id, target_date)` for the batch
- `process_claims_batch()` in `claim/services.py` — shared batch orchestration used by `ProcessClaimsMutation`

## Compatibility

- GraphQL `process_claims` contract unchanged
- Claim statuses, approved/valuated fields, and audit events preserved
- Removed redundant per-claim `save()` after `set_claim_processed_or_valuated` (status path already persists)

## Verification

- `claim/tests/test_batch_processing.py` — prefetch, ordering, policy cache, batch delegation
- Baseline comparison: `docs/BASELINE_BENCHMARK.md` scenario S5
