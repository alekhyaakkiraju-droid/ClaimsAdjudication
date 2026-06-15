# Opsera learning path — step by step (with demo script)

Use this as your personal curriculum. Complete each **Step** in order. Check the box when done.

**Time estimate:** Steps 1–5 (~2 hours theory + setup). Steps 6–10 (~4–6 hours hands-on). Step 11 = demo prep.

---

## Part A — Understand the landscape (before touching Opsera)

### Step 1 — What problem Opsera solves (15 min)

**Learn:**
- Teams use many tools: GitHub, AWS, Azure, Checkmarx, qTest, Sonar, Jira…
- Opsera **orchestrates** them in one pipeline with approvals, logs, and reports
- You do **not** replace GitHub Actions — you **combine** them (hybrid model)

**Draw this on a whiteboard for demo:**

```
Developer merges code
        ↓
   GitHub repo
        ↓
Opsera Pipeline starts  ──────────────────────────────┐
        ↓                                              │
   [GitHub Actions]  build · test · package           │
        ↓                                              │  One place to
   [Checkmarx]       security scan                     │  see status,
        ↓                                              │  approve,
   [qTest]           quality gate                      │  report
        ↓                                              │
   [Approval]        human gate (staging/prod)         │
        ↓                                              │
   [GitHub Actions]  deploy to AWS or Azure  ─────────┘
        ↓
   App running in cloud
```

**Quiz yourself:**
1. What does Opsera do that GitHub Actions alone does not? → *Approvals, tool aggregation, deployment reports, Checkmarx/qTest orchestration*
2. What does GitHub Actions still do? → *Actual build, test, docker, cloud CLI commands*

---

### Step 2 — Learn our two use cases (10 min)

| ID | Name | What you demo |
|----|------|----------------|
| **PY-01** | Module CI | "Code merges → automated quality + security gates" |
| **PY-02** | Container deploy | "Same pipeline family → ship to AWS **or** Azure" |

**Repo mapping:** We use `openimis-be-claim_py` (Python Django module) as the real app for PY-01.

Read: [deployment-matrix.md](deployment-matrix.md) — skim PY-01 and PY-02 rows.

---

### Step 3 — Learn the tools in the pipeline (20 min)

| Tool | Role | Where it runs | You must know |
|------|------|---------------|---------------|
| **GitHub Actions** | Build, test, deploy scripts | GitHub runners | Workflow YAML, `workflow_dispatch`, secrets |
| **Opsera Job Engine** | Orchestration, triggers GHA | Opsera platform | Pipeline steps, parameters, approvals |
| **Checkmarx** | SAST — finds code vulnerabilities | Opsera agent → Checkmarx server | Scan triggers after CI; High/Critical = fail |
| **qTest** | Test management / quality gate | Opsera → qTest | Test cycle must pass before promote |
| **SonarCloud** | Code quality (already on this repo) | GHA or Opsera | Quality gate on PRs |
| **AWS** | ECR (registry) + ECS (containers) | Cloud | IAM role, push image, update service |
| **Azure** | ACR + Web App for Containers | Cloud | Service principal, push image, update app |

**Hands-on:** Open these files and read top-to-bottom once:
- `.github/workflows/opsera-hybrid-python-ci.yml`
- `.github/workflows/opsera-hybrid-python-deploy.yml`

---

## Part B — Setup (do once)

### Step 4 — Access checklist (30 min)

Get from your team / Kumar:

- [ ] Opsera platform URL + login
- [ ] GitHub access to `alekhyaakkiraju-droid/ClaimsAdjudication` (or your fork)
- [ ] Permission to create Opsera pipelines
- [ ] Checkmarx project + Opsera Checkmarx agent configured
- [ ] qTest project (or agree to use **Manual Approval** for first demo)
- [ ] AWS dev account **or** Azure dev subscription (for PY-02 later)

**If qTest is not ready:** Say in demo: *"qTest step is represented by manual approval until test project is linked."*

---

### Step 5 — Register GitHub in Opsera (30 min)

In Opsera UI (exact menus vary by tenant version):

1. **Settings → Tools / Connectors → GitHub**
2. Connect organization/repo
3. Verify repo appears in pipeline GitHub Actions task dropdown

**Success criteria:** You can see `opsera-hybrid-python-ci.yml` when creating a GHA step.

**Document:** Screenshot + note any blockers in [deployment-matrix.md](deployment-matrix.md) → Team observations.

---

## Part C — Hands-on: PY-01 (CI pipeline)

### Step 6 — Run CI locally (20 min)

From repo root:

```bash
cd /path/to/openimis-be-claim_py

python3 -m venv .venv-opsera
source .venv-opsera/bin/activate
pip install build flake8 mypy pip-audit bandit django-stubs djangorestframework-stubs types-requests

python -m build
python -m flake8 claim --config=.flake8 --ignore W503,E501 --count
bash scripts/run-forge-mypy-gate.sh
bandit -r claim -lll -q
chmod +x scripts/verify-sibling-compatibility.sh && ./scripts/verify-sibling-compatibility.sh
```

**Success criteria:** All commands exit 0. You understand each gate.

**Demo talking point:** *"These same checks run in GitHub Actions when Opsera triggers the workflow."*

---

### Step 7 — Run CI in GitHub Actions (15 min)

1. Push branch with workflow files (or use `develop` if merged)
2. GitHub → **Actions** → **Opsera Hybrid Python CI**
3. **Run workflow** → `environment: dev`, `run_extended_tests: false`
4. Watch jobs complete; download **dist-** artifact

**Success criteria:** Green run + artifact uploaded.

**Screenshot for demo:** GHA summary showing "Opsera PY-01 CI Summary"

---

### Step 8 — Create PY-01 pipeline in Opsera (45 min)

Follow [blueprints/py-01-module-ci.md](blueprints/py-01-module-ci.md) exactly.

**Minimum viable pipeline (first time):**

| Order | Step type | Notes |
|-------|-----------|-------|
| 1 | GitHub Actions | `opsera-hybrid-python-ci.yml`, inputs: `environment=dev` |
| 2 | Manual approval | Placeholder for Checkmarx if agent not ready |
| 3 | Notification | Email/Slack "CI complete" (optional) |

**Then add:**
| 4 | Checkmarx | When credentials confirmed |
| 5 | qTest | When project linked |

**Run pipeline from Opsera.** Compare:
- Opsera Pipeline Activity log
- Linked GHA run URL
- Duration / status in Hummingbird (if enabled)

**Success criteria:** Opsera shows green; GHA link opens correct run.

---

## Part D — Hands-on: PY-02 (deploy pipeline)

### Step 9 — Dry-run deploy in GHA (15 min)

1. Actions → **Opsera Hybrid Python Deploy**
2. Inputs: `cloud_target=aws`, `environment=dev`, `dry_run=true`
3. Confirm: Docker image builds; **no** cloud push

**Success criteria:** Job green; logs say "Dry run: image built locally"

**Demo talking point:** *"dry_run=true lets us validate the pipeline without touching cloud."*

---

### Step 10 — Cloud deploy (1–2 hours, with team help)

Pick **one** cloud first (AWS **or** Azure).

**AWS:** Add secrets (repo Settings → Secrets):
- `AWS_OPSERA_DEPLOY_ROLE_ARN`
- `AWS_ECR_REPOSITORY`, `AWS_ECS_CLUSTER`, `AWS_ECS_SERVICE`, `AWS_REGION`

**Azure:** Add secrets:
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- `AZURE_ACR_NAME`, `AZURE_WEBAPP_NAME`, `AZURE_RESOURCE_GROUP`

Run deploy workflow: `dry_run=false`, `environment=dev`

Create Opsera pipeline PY-02 per [blueprints/py-02-container-deploy.md](blueprints/py-02-container-deploy.md)

**Success criteria:** Container running in dev; Opsera deployment report updated.

---

## Part E — Demo preparation

### Step 11 — Demo script (20 min prep, 15 min delivery)

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for word-for-word flow.

**Before demo:**
- [ ] PY-01 ran green in Opsera in last 24 hours
- [ ] GHA workflow run bookmarked
- [ ] One screenshot of Pipeline Activity
- [ ] Matrix doc open (Google Drive)
- [ ] Backup: video recording of successful run if live demo risky

---

## Part F — Learnings to capture (for Kumar / team)

After each step, add to **Team observations** in [deployment-matrix.md](deployment-matrix.md):

```markdown
### YYYY-MM-DD — Alekhya — Step N
- What worked:
- Blocker:
- Workaround:
- Best practice:
```

---

## Quick reference — file map

| Question | Answer in |
|----------|-----------|
| What use cases? | deployment-matrix.md |
| Opsera UI clicks? | blueprints/py-01-module-ci.md, py-02-container-deploy.md |
| What does GHA do? | .github/workflows/opsera-hybrid-*.yml |
| Java example? | examples/java-spring-opsera-gha.yml |
| Overview? | README.md |

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| Opsera can't see workflow | GitHub connector / wrong repo | Re-link; check branch |
| GHA not triggered | Wrong workflow filename | Match YAML name exactly |
| Checkmarx fails | Project preset / creds | Opsera admin + security team |
| qTest blocks | No test cycle | Use manual approval for demo |
| AWS deploy fails | IAM role trust / ECR | Verify OIDC + secrets |
| mypy fails locally | Missing stubs | `pip install django-stubs ...` |
| Extended tests fail | No assembly secret | Keep `run_extended_tests=false` |

---

## Suggested learning schedule

| Day | Focus |
|-----|--------|
| **Day 1** | Steps 1–3 (theory) + Step 6 (local CI) |
| **Day 2** | Steps 4–5 (access) + Step 7 (GHA CI) |
| **Day 3** | Step 8 (Opsera PY-01) + document learnings |
| **Day 4** | Steps 9–10 (deploy dry-run + one cloud) |
| **Day 5** | Step 11 (demo rehearsal) + matrix update |

---

**Next action for you:** Complete **Step 6** locally right now, then tell me which step you’re on and any blockers — we’ll go through it together.
