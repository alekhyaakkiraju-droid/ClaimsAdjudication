# Rollback runbook (WO-037)

Operational rollback procedures for high-risk modernization areas in this repository.

## General principles

1. **Stop traffic** to affected workers/API instances if errors spike.
2. **Revert package** to last known-good wheel/sdist version on PyPI or local artifact.
3. **Run verification queries** (see per-area checks below).
4. **Document** incident time, version rolled back from/to, and validation outcome.

Package install path: openIMIS backend assembly (`openimis-be_py`) pins module versions in its requirements.

---

## 1. Runtime / framework upgrade (WO-008, WO-009)

| Step | Action |
|------|--------|
| Rollback | Pin `openimis-be-claim` to previous release tag in assembly requirements |
| Verify | `python manage.py check claim`; smoke `manage.py test claim` |
| Notes | Python 3.11+ and Django 4.2 are assembly-wide — coordinate with platform team |

---

## 2. Authorization changes (WO-011, WO-012)

| Step | Action |
|------|--------|
| Rollback | Deploy previous module version **or** restore prior `ClaimConfig` permission keys in backend settings |
| Verify | GraphQL mutation without rights returns 403; REST `/claim/print/` enforces `claim_print_perms` |
| Risk | Users may gain/lose access abruptly — communicate to admins |

---

## 3. Redis query cache (WO-020)

| Step | Action |
|------|--------|
| Rollback | Set `query_cache_enabled = False` in `ClaimConfig` (no redeploy required) |
| Verify | Claim list/detail still return correct data; cache keys stop updating |
| Full revert | Deploy pre-WO-020 module if cache layer causes stale reads |

---

## 4. Database-backed job queue (WO-026)

| Step | Action |
|------|--------|
| Rollback | Set `job_queue_enabled = False` and `job_queue_async_threshold = 0` |
| Drain | Let `process_claim_jobs` worker finish in-flight jobs or mark failed |
| Verify | `processClaims` runs synchronously; no orphaned UI waiting on `claimJob` |
| Data | `tblClaimJob` rows are audit-only after rollback; no schema drop required |

---

## 5. Migrations (feedback assessment WO-032, job queue WO-026, etc.)

| Step | Action |
|------|--------|
| Rollback code | Deploy previous package **before** reversing migrations when possible |
| Reverse migration | `python manage.py migrate claim <previous_migration>` only if forward migration applied |
| WO-032 | `0038_rename_feedback_asessment_to_assessment` is Django-state only; reverse with `0037` if needed |

---

## 6. Report templates (WO-027)

| Step | Action |
|------|--------|
| Rollback | Previous package includes inline templates in Python |
| Verify | REST `/claim/print/?uuid=...` generates PDF without ReportBro load errors |

---

## Post-rollback health checks

```bash
# Module smoke (from assembly):
python manage.py test claim.tests.test_workflows claim.tests.test_gql_authorization

# REST smoke:
curl -H "Authorization: Bearer $TOKEN" "$BASE/claim/print/?uuid=$UUID" -o /dev/null -w '%{http_code}'

# GraphQL smoke: submitClaims on test claim in staging
```

## References

- **[RELEASE.md](RELEASE.md)** — publish and dry-run workflow
- **[STAGED_ROLLOUT.md](STAGED_ROLLOUT.md)** — phased deployment gates
- **[JOB_QUEUE.md](JOB_QUEUE.md)** — queue configuration keys
