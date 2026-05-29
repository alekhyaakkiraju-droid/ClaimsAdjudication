# Service boundaries (WO-029)

Split mixed responsibilities from monolithic module files into focused service and helper modules while preserving backward-compatible imports.

## Module layout

| Concern | Module |
|---------|--------|
| Claim CRUD / persistence | `claim/services/persistence.py` |
| Submission orchestration | `claim/services/submit.py` |
| Processing & batch | `claim/services/processing.py` |
| Feedback/review status | `claim/services/status.py` |
| Print/report data | `claim/services/report.py` |
| XML serialization | `claim/serializers/xml_serializer.py` |
| XML submit re-exports | `claim/services/xml_submit.py` |
| Attachment persistence | `claim/attachment_service.py` |
| GraphQL query resolvers | `claim/schema_resolvers.py` |
| Validation constants | `claim/validations/constants.py` |
| Dedrem processing | `claim/validations/dedrem.py` |
| Category derivation | `claim/validations/category.py` |
| Validation orchestration | `claim/validations/pipeline.py` |

## Backward compatibility

- `import claim.services` — unchanged public API via `claim/services/__init__.py`
- `import claim.validations` — unchanged via `claim/validations/__init__.py`
- `claim/schema.py` — thin GraphQL wiring; resolvers delegate to `schema_resolvers.py`
- `claim/gql_mutations.py` — attachment helpers delegate to `attachment_service.py`

## Tests

- `claim/tests/test_service_boundaries.py` — import and re-export checks
