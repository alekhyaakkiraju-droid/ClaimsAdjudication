# Claim read query optimization (WO-018)

Eager loading for GraphQL claim list/detail paths to eliminate N+1 queries on nested fields.

## Module

- `claim/read_queryset.py`:
  - `apply_claim_read_prefetches()` — nested `prefetch_related` only (safe with `gql_optimizer`)
  - `claim_read_queryset()` — full `select_related` + prefetches for single-claim lookups

## Integration points

- `claim/schema.py` — `resolve_claims`, `resolve_claim_history` use `apply_claim_read_prefetches()` before `gql_optimizer.query()`
- `claim/api_errors.py` — `get_valid_claim()` uses `claim_read_queryset()`
- `claim/gql_queries.py` — `ClaimGQLType` resolvers for items, services, attachments count, and client mutation id use prefetched caches when present

## Tests

- `claim/tests/test_claim_read_queryset.py` — prefetch cache hits and bounded query count for multi-claim list resolution
