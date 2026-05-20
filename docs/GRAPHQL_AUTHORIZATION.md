# GraphQL authorization (WO-011)

Claim GraphQL operations delegate permission checks to **`claim/gql_authorization.py`**.

## Central gateway

| Function | Use |
|----------|-----|
| `require_query_permission(info, operation)` | Query resolvers and `ClaimGQLType` field resolvers |
| `require_mutation_permission(user, mutation_class)` | `OpenIMISMutation.async_mutate` by `_mutation_class` |
| `require_authenticated_mutation_user(user)` | Create/update claim mutations requiring login |

## Permission maps

- **`GQL_QUERY_PERMISSION_MAP`** — `claims`, `claim`, `claim_attachments`, `claim_officers`, etc.
- **`GQL_MUTATION_PERMISSION_MAP`** — `CreateClaimMutation`, `SubmitClaimsMutation`, …

Rights resolve from `ClaimConfig` (loaded from `ModuleConfiguration` in `apps.py`).

### Special rules

| Operation | Rule |
|-----------|------|
| `claims`, `claim`, `claim_history` | Deny only when `ROW_SECURITY=True` and user lacks `gql_query_claims_perms` |
| `insuree_name_by_chfid` | Requires **create** OR **update** claim mutation rights |
| `claim_attachments` | Requires `gql_query_claims_perms`; resolver returns valid attachment queryset |

## Adding a new GraphQL operation

1. Add entry to the appropriate map in `gql_authorization.py`.
2. Call `require_query_permission` or `require_mutation_permission` from the resolver/mutation.
3. Extend `claim/tests/test_gql_authorization.py` and permission characterization tests.

## Audit

```python
from claim.gql_authorization import list_query_operations, list_mutation_classes
```
