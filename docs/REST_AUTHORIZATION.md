# REST authorization (WO-012)

Claim REST endpoints use **`claim/rest_authorization.py`**, aligned with the GraphQL gateway in `claim/gql_authorization.py`.

## Endpoints

| Path | Permission (`ClaimConfig`) | Notes |
|------|---------------------------|-------|
| `GET /claim/print/` | `claim_print_perms` | Claim report PDF |
| `GET/POST /claim/attach/` | `gql_query_claims_perms` | Attachment download |

## HTTP semantics

| Case | Status |
|------|--------|
| Authenticated, missing rights | **403** (`PermissionDenied` via DRF) |
| Authenticated, rights OK, attachment missing / out of row scope | **404** |
| Authenticated, rights OK, attachment empty on disk/DB | **404** |
| Success | **200** |

Row-security filtering on `/claim/attach/` is unchanged: `LocationManager` filters by `health_facility__location` when `ROW_SECURITY=True`.

## Adding a REST endpoint

1. Add entry to `REST_ENDPOINT_PERMISSIONS` in `rest_authorization.py`.
2. Decorate the view with `@permission_classes([ClaimRestPermission("…")])`.
3. Return **404** for missing resources; reserve **403** for authorization failures only.
