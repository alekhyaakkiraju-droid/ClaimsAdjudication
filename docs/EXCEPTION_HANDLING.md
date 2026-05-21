# Exception handling (WO-014)

## Safe lookups (`claim/api_errors.py`)

| Helper | Behavior |
|--------|----------|
| `get_valid_claim` | Returns claim or `None` (no `DoesNotExist`) |
| `get_insuree_health_facility_for_fsp` | Returns health facility or `None` (fixes FSP NPE) |
| `claim_not_found_errors` | Structured mutation error list |
| `mutation_error_list` | Logs unexpected errors; omits internal details from clients |

## GraphQL resolvers

- `resolve_claim` — uses `get_valid_claim`; missing records return `null`
- `resolve_fsp_from_claim` — uses `get_insuree_health_facility_for_fsp`; missing insuree returns `null`

## Mutations

- `SaveClaimReviewMutation` / `DeliverClaimFeedbackMutation` — safe claim lookup before processing
- Broad `except Exception` handlers return `mutation_error_list` without leaking `str(exc)` for unexpected failures

## REST

- `/claim/attach/` — missing attachment returns **404** (WO-012)
- `ClaimReportService.fetch` — missing claim raises `PermissionDenied` (existing)
