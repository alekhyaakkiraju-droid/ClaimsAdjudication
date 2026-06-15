# Deployment matrix — additions for Google Drive master doc

Copy these rows into the team matrix. Status column is for your validation notes.

---

## PY-01 — Python openIMIS module CI (security + quality)

**App:** `openimis-be-claim_py` (Django pluggable module)  
**Tech:** Python 3.11, Django 4.2  
**Orchestrator:** Opsera Job Engine  
**CI runner:** GitHub Actions  
**Cloud:** Artifact only (wheel/sdist → GitHub Actions artifact; optional S3 via secrets)

| Dimension | Value |
|-----------|--------|
| **Trigger** | Opsera manual / webhook on PR merge to `develop` |
| **Build** | `python -m build` (pyproject.toml) |
| **Unit test** | `manage.py test claim` (requires assembly secrets in GHA) |
| **Lint / type** | flake8, mypy (`scripts/run-forge-mypy-gate.sh`) |
| **SAST (in GHA)** | Bandit high severity |
| **Dependency scan** | pip-audit |
| **Secret scan** | Gitleaks |
| **SAST (Opsera agent)** | Checkmarx scan — team Checkmarx project |
| **Quality gate** | qTest — link test run / pass threshold before promote |
| **Sonar** | SonarCloud (existing module CI) |
| **Approval** | Opsera manual gate before artifact promote |
| **Rollback** | Re-run pipeline with previous git tag; pin assembly version |

**GHA workflow:** `.github/workflows/opsera-hybrid-python-ci.yml`

**Opsera blueprint:** [blueprints/py-01-module-ci.md](blueprints/py-01-module-ci.md)

**Validation checklist:**

- [ ] Opsera triggers GHA with `environment=dev`
- [ ] Checkmarx step completes; defects triaged
- [ ] qTest gate blocks on fail
- [ ] Artifact downloadable from GHA run
- [ ] Pipeline Activity log captured in Opsera

**Team observations:** _(add date, name, notes)_

---

## PY-02 — Python container deploy (AWS or Azure)

**App:** openIMIS backend assembly image (claim module as dependency) — *or* standalone demo Flask/FastAPI wrapper for learning  
**Tech:** Python 3.11, Docker  
**Orchestrator:** Opsera Job Engine  
**Deploy runner:** GitHub Actions  
**Cloud targets:** AWS ECS (Fargate) **or** Azure Web App for Containers

| Dimension | AWS | Azure |
|-----------|-----|-------|
| **Registry** | ECR | Azure Container Registry (ACR) |
| **Runtime** | ECS Fargate service | Web App for Containers |
| **Deploy mechanism** | `aws ecs update-service` | `az webapp config container set` |
| **Secrets** | AWS Secrets Manager / SSM | Key Vault references |
| **Networking** | VPC, ALB | VNet, App Gateway (optional) |

| Pipeline stage | Tool |
|----------------|------|
| CI | PY-01 or reuse forge-quality-gates |
| Container build | Docker build in GHA |
| Scan image | Checkmarx (Opsera) or Trivy (GHA optional) |
| Deploy dev | Auto on `develop` |
| Deploy staging | Opsera approval gate |
| Deploy prod | Opsera approval + change window |

**GHA workflow:** `.github/workflows/opsera-hybrid-python-deploy.yml`

**Opsera blueprint:** [blueprints/py-02-container-deploy.md](blueprints/py-02-container-deploy.md)

**Pipeline parameters (Opsera runtime):**

| Parameter | Values | Required |
|-----------|--------|----------|
| `cloud_target` | `aws` \| `azure` | Yes |
| `environment` | `dev` \| `staging` \| `prod` | Yes |
| `image_tag` | git SHA or semver | Yes |
| `dry_run` | `true` \| `false` | No (default `true` for first tests) |

**Validation checklist:**

- [ ] AWS path: ECR push + ECS service update (dev)
- [ ] Azure path: ACR push + Web App container update (dev)
- [ ] Opsera approval blocks staging/prod
- [ ] Rollback: redeploy previous `image_tag`

**Team observations:** _(add date, name, notes)_

---

## JAVA-01 — Reference row (not in this repo)

**App:** Spring Boot REST API (external sample repo)  
**GHA reference:** [examples/java-spring-opsera-gha.yml](examples/java-spring-opsera-gha.yml)

| Dimension | Value |
|-----------|--------|
| Build | Maven `mvn -B package` |
| Test | JUnit + Sonar |
| Checkmarx | Opsera agent |
| qTest | Opsera agent |
| AWS deploy | Elastic Beanstalk or ECS |
| Azure deploy | App Service Java SE |

**Status:** Template only — implement in separate Java sample repo.

---

## Matrix expansion template

```markdown
## {ID} — {Title}

**App:**  
**Tech:**  
**Orchestrator:** Opsera  
**CI/CD:** GitHub Actions | Opsera Job Engine | Other  
**Cloud:** AWS | Azure | Both  

| Stage | Tool | Gate |
|-------|------|------|
| | | |

**Observations:**
```
