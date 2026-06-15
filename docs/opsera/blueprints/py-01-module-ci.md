# Opsera blueprint: PY-01 — Python module CI

Create this pipeline in **Opsera → Pipelines → New Pipeline**.

## Pipeline metadata

| Field | Value |
|-------|--------|
| Name | `PY-01-openimis-claim-module-ci` |
| Description | Python module build, test, security — openimis-be-claim_py |
| Tags | `python`, `aws-learning`, `github-actions`, `checkmarx`, `qtest` |

## Global / pipeline-level parameters

Enable **Dynamic Settings** so Opsera prompts at run time:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `environment` | string | `dev` | dev / staging / prod label for reporting |
| `run_extended_tests` | boolean | `false` | Assembly integration tests (needs secrets) |
| `checkmarx_threshold` | string | `high` | Fail gate severity |

## Step sequence

### Step 1 — GitHub Actions: CI workflow

| Setting | Value |
|---------|--------|
| Task type | GitHub Actions |
| Repository | `alekhyaakkiraju-droid/ClaimsAdjudication` |
| Workflow file | `opsera-hybrid-python-ci.yml` |
| Branch | `develop` |
| Inputs | Map pipeline params → workflow `workflow_dispatch` inputs |

**Pass at runtime:**

```json
{
  "environment": "{{ pipeline.environment }}",
  "run_extended_tests": "{{ pipeline.run_extended_tests }}"
}
```

**Success criteria:** GHA job `opsera-ci` green.

**Observed learning:** Note GHA run URL in Pipeline Activity; compare duration in Hummingbird summary.

---

### Step 2 — Checkmarx SAST (Opsera agent)

| Setting | Value |
|---------|--------|
| Task type | Checkmarx (Tools Registry) |
| Project | Team Checkmarx project for Python |
| Source | Git commit from Step 1 (Opsera captures commit ID) |
| Scan type | Full / incremental per team policy |

**Gate:** Fail pipeline if new High/Critical above threshold.

**Blocker notes to document:**

- Agent connectivity to Checkmarx server
- Project preset for Python/Django
- False positive triage process

---

### Step 3 — qTest quality gate

| Setting | Value |
|---------|--------|
| Task type | qTest integration |
| Test cycle | Link to regression cycle for claim module / smoke |
| Gate | Minimum pass % (e.g. 95%) or critical test cases all pass |

**Gate:** Block promote if qTest cycle fails.

**If qTest not ready:** Use **Manual Approval** placeholder with checklist until qTest project is configured.

---

### Step 4 — SonarCloud verification (optional)

If not fully covered in GHA, add Opsera task to poll Sonar quality gate API for PR/commit.

Existing module key: `alekhyaakkiraju-droid_openimis-be-claim_py`

---

### Step 5 — Manual approval (staging/prod only)

| Setting | Value |
|---------|--------|
| Condition | Run when `environment` in (`staging`, `prod`) |
| Approvers | Team lead / Kumar's group |

Opsera records approver identity in Pipeline Activity (2024 feature).

---

### Step 6 — Publish artifact marker

| Setting | Value |
|---------|--------|
| Task type | Notification or custom webhook |
| Action | Tag successful build in Opsera deployment report |

Downstream PY-02 pipeline can consume `image_tag` / artifact version.

## Failure handling

| Failure | Action |
|---------|--------|
| GHA lint/test fail | Fix code; re-run from Step 1 |
| Checkmarx high findings | Triage; waivers via security team |
| qTest fail | Block; open defect |
| Sonar fail | Fix hotspots; re-run |

## Evidence to capture for team KB

1. Screenshot of Opsera Pipeline Activity with all steps green  
2. GHA run link + duration  
3. Checkmarx scan ID + defect count  
4. qTest cycle link + pass rate  
5. Blockers and workarounds (1–2 sentences each)
