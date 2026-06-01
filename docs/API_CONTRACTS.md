# API contracts (WO-034)

Consumer-facing documentation for the claim module GraphQL and REST surfaces after modernization (authorization, errors, permissions).

## GraphQL

Schema wiring: `claim/schema.py` (descriptions on `Query` / `Mutation` fields).

Permission gateway: **[GRAPHQL_AUTHORIZATION.md](GRAPHQL_AUTHORIZATION.md)** — every query/mutation maps to `ClaimConfig` permission keys via `claim/gql_authorization.py`.

### Error shape

Mutations return OpenIMIS-standard error lists from `claim/api_errors.py`:

```json
[{ "message": "translated key or text", "detail": "optional validation detail" }]
```

- **401/403**: unauthenticated or missing permission (`PermissionDenied` / auth validation).
- **Not found**: `claim_not_found_errors()` for missing claim UUID.
- Unexpected exceptions are logged server-side; clients receive generic mutation failure messages (WO-014).

### Key queries

| Field | Permission | Notes |
|-------|------------|-------|
| `claims` | Row-security + `gql_query_claims_perms` | Filterable list; prefetched reads |
| `claim` | Same as list | By `id` or `uuid` |
| `validateClaimCode` | `gql_query_claims_perms` | Uniqueness check |
| `claimJob` / `claimJobs` | `gql_mutation_process_claims_perms` | Async batch status |

### Key mutations

| Field | Permission config key |
|-------|----------------------|
| `createClaim` | `gql_mutation_create_claims_perms` |
| `submitClaims` | `gql_mutation_submit_claims_perms` |
| `processClaims` | `gql_mutation_process_claims_perms` |
| `deliverClaimFeedback` | `gql_mutation_deliver_claim_feedback_perms` |

Full mutation map: `GQL_MUTATION_PERMISSION_MAP` in `claim/gql_authorization.py`.

## REST

Endpoints in `claim/views.py`; permissions via **[REST_AUTHORIZATION.md](REST_AUTHORIZATION.md)**.

| Method | Path | Permission | Behavior |
|--------|------|------------|----------|
| GET | `/claim/print/` | `claim_print_perms` | Generate claim PDF via ReportBro (`uuid` query param) |
| GET/POST | `/claim/attach/` | `gql_query_claims_perms` | Download attachment binary (`id` query param); 404 when missing or out of scope |

Row security applies to attachment download when `ROW_SECURITY` is enabled.

## Configuration

Module settings are exposed on `ClaimConfig` (`claim/apps.py`) — see README configuration keys for GraphQL permission attribute names.

## Verification

- `claim/tests/test_gql_authorization.py` — permission map coverage
- `claim/tests/test_rest_authorization.py` — REST permission classes
