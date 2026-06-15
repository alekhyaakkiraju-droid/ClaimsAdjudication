# Opsera deployment pipelines — hands-on starter kit

Goal: gain hands-on experience with **Opsera Job Engine** + **GitHub Actions** hybrid pipelines on **AWS** and **Azure**, with security (Checkmarx) and quality (qTest) gates.

This folder supports the team deployment matrix. Start with **two Python use cases** grounded in this repo, then extend to Java/.NET.

## Hybrid model (Opsera + GitHub Actions)

```
Opsera Pipeline (orchestrator)
  │
  ├─ Step 1: Trigger GitHub Actions  ──►  .github/workflows/opsera-hybrid-python-ci.yml
  ├─ Step 2: Checkmarx scan (Opsera agent)
  ├─ Step 3: qTest quality gate (Opsera agent)
  ├─ Step 4: Manual approval (staging/prod)
  └─ Step 5: Trigger GitHub Actions  ──►  .github/workflows/opsera-hybrid-python-deploy.yml
                                              (AWS ECS or Azure Web App)
```

Opsera provides: orchestration, approvals, Checkmarx/qTest integration, centralized logs, Hummingbird AI analysis.

GitHub Actions provides: build, test, package, cloud deploy scripts.

Reference: [Opsera GitHub Actions integration](https://docs.opsera.io/opsera-release-updates/release-update-03-20-2024)

## Use cases in this repo

| ID | Use case | Matrix row | GHA workflow | Cloud |
|----|----------|------------|--------------|-------|
| **PY-01** | Python module CI + security + quality | [deployment-matrix.md](deployment-matrix.md#py-01) | `opsera-hybrid-python-ci.yml` | N/A (artifact) |
| **PY-02** | Python container deploy | [deployment-matrix.md](deployment-matrix.md#py-02) | `opsera-hybrid-python-deploy.yml` | AWS ECS **or** Azure Web App |

## Quick start (Alekhya / team)

### 1. Register tools in Opsera

- GitHub connector → `alekhyaakkiraju-droid/ClaimsAdjudication` (or your fork)
- AWS account + ECR/ECS **or** Azure subscription + Web App
- Checkmarx agent (team credentials)
- qTest project linkage

### 2. Create pipeline PY-01 in Opsera UI

Follow step order in [blueprints/py-01-module-ci.md](blueprints/py-01-module-ci.md).

### 3. Create pipeline PY-02 in Opsera UI

Follow [blueprints/py-02-container-deploy.md](blueprints/py-02-container-deploy.md).

### 4. Validate

```bash
# Local smoke (same steps as GHA CI job)
python -m flake8 claim --config=.flake8 --ignore W503,E501
bash scripts/run-forge-mypy-gate.sh
python -m build
```

Trigger from Opsera with pipeline parameters:

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `environment` | `dev` / `staging` / `prod` | Target env label |
| `run_security_gates` | `true` | Skip or enforce extra checks |
| `cloud_target` | `aws` / `azure` | PY-02 only |

### 5. Document learnings

Add rows to [deployment-matrix.md](deployment-matrix.md) under **Team observations**.

## Files

| Path | Purpose |
|------|---------|
| [deployment-matrix.md](deployment-matrix.md) | Matrix rows + expansion template |
| [blueprints/py-01-module-ci.md](blueprints/py-01-module-ci.md) | Opsera step-by-step PY-01 |
| [blueprints/py-02-container-deploy.md](blueprints/py-02-container-deploy.md) | Opsera step-by-step PY-02 |
| [examples/java-spring-opsera-gha.yml](examples/java-spring-opsera-gha.yml) | Java reference workflow for matrix |
| `../../.github/workflows/opsera-hybrid-python-ci.yml` | GHA CI for Opsera trigger |
| `../../.github/workflows/opsera-hybrid-python-deploy.yml` | GHA deploy for Opsera trigger |

## Next matrix expansions (not implemented yet)

| Tech | Suggested use case |
|------|-------------------|
| Java | Spring Boot JAR → AWS Elastic Beanstalk / Azure App Service |
| .NET | ASP.NET Core → Azure App Service |
| SQL | Flyway/Liquibase migration pipeline with rollback gate |
| Informatica | ICS job export → promote DEV→QA→PROD |
| Apigee | Proxy bundle deploy via Maven + Apigee management API |

## Opsera MCP note

If using Cursor Opsera MCP (`user-opsera-dev`), ensure the server is connected in **Cursor Settings → MCP**. It was unavailable during initial setup; pipelines here use GHA + documented Opsera blueprints instead.
