# Claim creation write optimization (WO-016)

## Change

`process_child_relation` in `claim/utils.py` batches **new** child records:

- **Items** — `ClaimItem.objects.bulk_create` for new rows in `process_child_relation`
- **Services** — still use `service_create_hook` per row (versioned `ClaimService` + sub-elements need individual `create()` for reliable FKs in CI/PostgreSQL)

Updates to historized rows still use per-row `save()` (unchanged).

## Compatibility

- Claimed totals use the same `calcul_amount_service` logic before persistence.
- GraphQL create-claim payloads and response shape are unchanged.
- `item_create_hook` / `service_create_hook` remain for non-batched callers.

## Verification

- `claim/tests/test_bulk_claim_writes.py` — asserts `bulk_create` usage and claimed totals.
- Existing `test_process_child_relation_*` workflow tests in `test_workflows.py`.
