# Opsera blueprint: PY-02 — Python container deploy (AWS / Azure)

Create this pipeline in **Opsera → Pipelines → New Pipeline**.

Depends on **PY-01** passing (or equivalent CI green on target commit).

## Pipeline metadata

| Field | Value |
|-------|--------|
| Name | `PY-02-python-container-deploy` |
| Description | Build Docker image, deploy to AWS ECS or Azure Web App |
| Tags | `python`, `docker`, `aws`, `azure`, `github-actions` |

## Pipeline-level parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cloud_target` | choice | `aws` | `aws` or `azure` |
| `environment` | choice | `dev` | dev / staging / prod |
| `image_tag` | string | `{commit_sha}` | Docker tag |
| `dry_run` | boolean | `true` | Build only; skip cloud deploy |

## Prerequisites (one-time)

### AWS path

- ECR repository: `opsera-learning/claim-backend` (example)
- ECS cluster + service (Fargate)
- IAM role for GHA OIDC: `GitHubActionsOpseraDeploy`
- Secrets in GitHub: `AWS_ROLE_ARN`, `AWS_REGION`, `ECS_CLUSTER`, `ECS_SERVICE`

### Azure path

- ACR: `opseralearning.azurecr.io`
- Web App for Containers
- Service principal or federated credential for GHA
- Secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_WEBAPP_NAME`

## Step sequence

### Step 1 — GitHub Actions: deploy workflow

| Setting | Value |
|---------|--------|
| Task type | GitHub Actions |
| Workflow file | `opsera-hybrid-python-deploy.yml` |
| Inputs | See below |

```json
{
  "cloud_target": "{{ pipeline.cloud_target }}",
  "environment": "{{ pipeline.environment }}",
  "image_tag": "{{ pipeline.image_tag }}",
  "dry_run": "{{ pipeline.dry_run }}"
}
```

**Success criteria:** Job completes; ECR/ACR push succeeds (unless dry_run).

---

### Step 2 — Checkmarx (container / IaC if applicable)

Optional container scan step if team enables Checkmarx CxSAST for Docker layers.

---

### Step 3 — Smoke test

| AWS | Azure |
|-----|-------|
| Curl ALB health endpoint | Curl Web App `/health` |
| Or ECS task health | Application Insights availability |

Can be GHA step inside deploy workflow or separate Opsera HTTP task.

---

### Step 4 — Manual approval

Required when:

- `environment` = `staging` or `prod`
- `dry_run` = `false`

---

### Step 5 — Deployment report

Opsera deployment report captures internal + external deploys (2024 feature). Mark success for team dashboard.

## Rollback procedure

1. Re-run pipeline with previous known-good `image_tag`
2. Or Opsera child pipeline `PY-02-rollback` pointing to last green deployment record
3. Document in team KB: rollback took X minutes; any data migration concerns N/A for stateless container

## Branching: AWS vs Azure in one pipeline

Use Opsera **conditional step** on `cloud_target`:

```
if cloud_target == "aws"  → GHA inputs cloud_target=aws
if cloud_target == "azure" → GHA inputs cloud_target=azure
```

Single blueprint; two validated paths for matrix completeness.

## Learning goals for working session

- [ ] Successfully deploy to **AWS dev** with `dry_run=false`
- [ ] Successfully deploy to **Azure dev** with `dry_run=false`
- [ ] Compare: credential setup, deploy time, log visibility in Opsera vs GHA alone
- [ ] Document one blocker per cloud in deployment-matrix.md
