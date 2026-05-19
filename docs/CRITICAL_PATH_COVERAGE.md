# Critical path test coverage (WO-004)

**Work order:** WO-004 — Expand critical path coverage  
**PRD target:** ≥60% line coverage on critical paths (REQ-008 / US-12)

## Critical paths

| Area | Module files |
|------|----------------|
| Claim submission | `claim/services.py` (`ClaimSubmitService`, `ClaimCreateService`) |
| Processing / validation | `claim/services.py`, `claim/validations.py` |
| GraphQL API | `claim/schema.py`, `claim/gql_mutations.py`, `claim/gql_queries.py` |
| Utilities | `claim/utils.py` (`process_child_relation`, `approved_amount`) |
| REST / reports | `claim/views.py`, `ClaimReportService` in `claim/services.py` |

## Test suite

| File | Scope |
|------|--------|
| `claim/tests/test_critical_paths.py` | Integration: submit/query flows, attachments, validation edges, report data |
| `claim/tests/test_workflows.py` | Workflow characterization (WO-002) |
| `claim/tests/test_permissions.py` | Permission characterization (WO-003) |
| `claim/tests/test_validations.py` | Validation rules |
| `claim/tests/tests_services.py` | Submit service, XML, hooks |
| `claim/tests/report.py` | REST print + report service |

## Measuring coverage (parent backend)

From [openimis-be_py](https://github.com/openimis/openimis-be_py) with this module installed:

```bash
pip install coverage
cd openIMIS
coverage run --rcfile=../../current-module/.coveragerc manage.py test claim
coverage report --rcfile=../../current-module/.coveragerc
```

Or use `scripts/check-critical-path-coverage.sh` from this repo root (requires `OPENIMIS_MANAGE_PY`).

CI runs the full `claim` module test suite via `.github/workflows/ci.yml` → `ci_module.yml`; Sonar sources are `claim` with test exclusions.

## Acceptance criteria

- [x] Tests expand coverage on submission, query, attachment, validation, and report paths
- [x] `.coveragerc` enforces 60% `fail_under` on critical path sources
- [x] Integration tests use existing GraphQL/REST backend interfaces
