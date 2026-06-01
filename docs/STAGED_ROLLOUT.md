# Staged rollout (WO-038)

Controlled release path from development validation through pilot to production-ready publication.

## Stages

| Stage | Gate | Smoke checks |
|-------|------|--------------|
| **1. Development** | All WO PRs merged to `develop`; CI green | `forge-quality-gates.yml`, `ci_module.yml`, SonarCloud |
| **2. Staging** | Assembly deploys tagged RC from `develop` | `./scripts/validate-security-controls.sh`, `./scripts/validate-performance-targets.sh`, `manage.py test claim` |
| **3. Pilot** | Limited HF/users on staging clone | S1–S5 benchmarks per [PERFORMANCE_VALIDATION.md](PERFORMANCE_VALIDATION.md); manual claim lifecycle |
| **4. Production-ready** | GitHub Release `vX.Y.Z` → PyPI | [RELEASE.md](RELEASE.md) dry-run then publish |

## Pre-flight checklist

- [ ] [API_CONTRACTS.md](API_CONTRACTS.md) reviewed by integration team
- [ ] [SECURITY_VALIDATION.md](SECURITY_VALIDATION.md) scenarios pass on staging
- [ ] [PERFORMANCE_VALIDATION.md](PERFORMANCE_VALIDATION.md) S1–S5 recorded
- [ ] [ROLLBACK_RUNBOOK.md](ROLLBACK_RUNBOOK.md) distributed to operations
- [ ] [SIBLING_COMPATIBILITY.md](SIBLING_COMPATIBILITY.md) verified in assembly

## Smoke validation script

```bash
./scripts/staged-rollout-smoke.sh
```

## Publication

1. Merge `develop` → release branch per team process.
2. Create GitHub Release with tag `vX.Y.Z` (see [RELEASE.md](RELEASE.md)).
3. Confirm PyPI artifact version matches tag.
4. Update assembly requirements pin in openimis-be_py.

## Rollback

If pilot fails, follow [ROLLBACK_RUNBOOK.md](ROLLBACK_RUNBOOK.md) before promoting to production.

## Record template

| Stage | Date | Version | Validator | Result | Notes |
|-------|------|---------|-----------|--------|-------|
| Staging | | | | | |
| Pilot | | | | | |
| Production | | | | | |
