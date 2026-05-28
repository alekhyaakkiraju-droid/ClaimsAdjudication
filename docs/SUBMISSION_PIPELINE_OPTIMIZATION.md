# Submission pipeline optimization (WO-017)

## Change

`claim/submission_pipeline.py` centralizes eager loading for the submit path:

- `claim_submission_queryset()` — `select_related` for health facility (incl. pricelists), insuree, admin; `prefetch_related` for active items/services
- `load_claim_for_submission()` — reload by id before `save_history` / validation

`ClaimSubmitService.submit_claim` always reloads with prefetches (one round-trip vs N+1 during validation).

`enter_and_submit` passes `skip_hf_validation=True` because HF was validated during create.

`SubmitClaimsMutation` reuses `claim_submission_queryset()` instead of inline prefetch blocks.

## Compatibility

- GraphQL submit/create contracts unchanged
- Validation errors still returned via existing `processing_claim` paths
- HF row-security check still runs on standalone `submit_claim` calls

## Verification

- `claim/tests/test_submission_pipeline.py` — prefetch cache and HF skip behavior
- Existing `test_claim_enter_and_submit` in `tests_services.py`
- Baseline comparison: `docs/BASELINE_BENCHMARK.md` scenario S1
