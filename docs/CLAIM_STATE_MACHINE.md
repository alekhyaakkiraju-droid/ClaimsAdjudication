# Claim lifecycle state machine (WO-021)

Explicit transition rules for claim status integers used across services, validations, and GraphQL mutations.

## Module

- `claim/state_machine.py`
  - `ALLOWED_TRANSITIONS` — valid forward transitions preserving existing status integers
  - `apply_claim_status(claim, new_status)` — validates then assigns status
  - `ClaimStatusTransitionError` — structured error for invalid transitions

## Integration points

- `claim/services.py` — submit and process/valuate paths
- `claim/validations.py` — validation-driven rejections and final status updates
- `claim/gql_mutations.py` — review mutation rejection path

## Tests

- `claim/tests/test_state_machine.py` — transition rules and service integration
