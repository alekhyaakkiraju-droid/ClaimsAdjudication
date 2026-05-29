# Feedback and review state machines (WO-022)

Explicit transition rules for `feedback_status` and `review_status` integers used across services, validations, and GraphQL mutations.

## Module

- `claim/feedback_review_state_machine.py`
  - `FEEDBACK_ALLOWED_TRANSITIONS` / `REVIEW_ALLOWED_TRANSITIONS`
  - `apply_feedback_status(claim, new_status)` / `apply_review_status(claim, new_status)`
  - `FeedbackReviewStatusTransitionError` — structured error for invalid transitions

## Integration points

- `claim/services.py` — `set_claims_status` for feedback/review mutations
- `claim/gql_mutations.py` — deliver feedback and save review submission paths
- `claim/validations.py` — processing auto-bypass from selected to bypassed

## Tests

- `claim/tests/test_feedback_review_state_machine.py` — transition rules and service integration
