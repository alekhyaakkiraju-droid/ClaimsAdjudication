# Claim restore rules (WO-024)

Formalized validation for restoring rejected claims via the `restore` foreign key.

## Module

- `claim/claim_restore.py`
  - `validate_restore_request(restore_uuid, user)` — permission, source existence, status, and max-restore checks
  - `count_restores_for_source(source_claim)` — counts valid restore claims for limit enforcement
  - `require_restore_permission(user)` in `claim/gql_authorization.py` — restore-specific permission gate

## Rules

1. Caller must hold `ClaimConfig.gql_mutation_restore_claims_perms` (default right `111012`).
2. Source claim must exist, be valid (`validity_to` is null), and have status `STATUS_REJECTED`.
3. When `ClaimConfig.claim_max_restore` is set, the count of valid restore claims for the same source must stay below that limit.
4. When `claim_max_restore` is `None`, no maximum is enforced.

## Integration points

- `claim/services.py` — `claim_create` and `validate_claim_data` delegate to `validate_restore_request`
- `claim/gql_mutations.py` — restore UUID on create/update mutations
- `claim/audit_governance.py` — `claim.restore` is a significant audit operation

## Tests

- `claim/tests/test_claim_restore.py` — permission, validation, max-restore, and FK linkage
