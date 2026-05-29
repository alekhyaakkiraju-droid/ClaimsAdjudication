# Security validation (WO-036)

Focused security validation for the modernized claim module before release.

## Scope

| Area | Implementation | Validation |
|------|----------------|------------|
| Broken access control | `claim/gql_authorization.py`, `claim/rest_authorization.py` | Permission map tests |
| Attachment misuse | `claim/attachment_validation.py` | MIME/size/strategy tests |
| Exception leakage | `claim/api_errors.py` | Mutation error shape tests |
| Audit trail | `claim/audit_governance.py` | Mutation audit tests |
| CI gates | `forge-quality-gates.yml`, `ci_module.yml` | Gitleaks, Bandit, pip-audit |

## Scenarios

### GraphQL authorization

- Unauthenticated mutation → `mutation.authentication_required`
- Authenticated user without rights → `unauthorized` (403)
- Covered by: `claim/tests/test_gql_authorization.py`, `test_workflows.py`

### REST authorization

- `/claim/print/` requires `claim_print_perms`
- `/claim/attach/` requires query claims permission + row security
- Covered by: `claim/tests/test_rest_authorization.py`

### Attachment validation

- Reject invalid MIME, oversize payloads, unknown strategies
- Covered by: `claim/tests/test_attachment_validation.py`

### Exception handling

- Unexpected errors logged; clients receive generic messages
- Covered by: `claim/tests/test_api_errors.py` (if present) / mutation paths

## CI / pipeline verification

Run locally or verify on PR:

```bash
# Secret scan + SAST + dependency audit (WO-007)
# Triggered by forge-quality-gates.yml on PR
python -m flake8 claim
bash scripts/run-forge-mypy-gate.sh
```

Workflows: gitleaks (full history), bandit (high severity), pip-audit on direct deps.

## Validation record (2026-05-29)

| Check | Result | Evidence |
|-------|--------|----------|
| GraphQL permission maps complete | **Pass** | `test_gql_authorization.py` |
| REST permission classes wired | **Pass** | `test_rest_authorization.py` |
| Attachment validation enforced | **Pass** | `test_attachment_validation.py` |
| Audit on sensitive mutations | **Pass** | `test_audit_governance.py` |
| CI security gates present | **Pass** | `docs/FORGE_CI_GATES.md` |

**Residual risks:** Enterprise penetration testing and production WAF rules are out of module scope.

## Script

```bash
./scripts/validate-security-controls.sh
```
