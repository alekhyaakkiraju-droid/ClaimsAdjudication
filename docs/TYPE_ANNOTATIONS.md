# Type annotations (WO-031)

Public service and API-facing modules now carry explicit type hints to support static checking in CI.

## Typed modules (strict mypy overrides)

| Module | Scope |
|--------|--------|
| `claim/serializers/xml_serializer.py` | XML submission DTOs |
| `claim/services/submit.py` | Submission and creation services |
| `claim/attachment_service.py` | Attachment persistence |
| `claim/api_errors.py` | Safe lookups and error shapes |
| `claim/gql_authorization.py` | GraphQL permission gateway |
| `claim/rest_authorization.py` | REST permission gateway |
| `claim/schema_resolvers.py` | GraphQL query resolvers |

## CI gate

`scripts/run-forge-mypy-gate.sh` runs mypy with `[tool.mypy.overrides]` enforcing `disallow_untyped_defs` on the modules above. Legacy modules remain in baseline mode until incrementally typed.

## Local check

```bash
pip install mypy
bash scripts/run-forge-mypy-gate.sh
```
