# Demo script — Opsera + GitHub Actions (15 minutes)

Audience: team working session (Kumar + peers)  
Goal: show hands-on learning with PY-01 (CI) and intro to PY-02 (deploy)

---

## Before you start (5 min prior)

- [ ] Opsera logged in; PY-01 pipeline open in one tab
- [ ] GitHub Actions last green run open in second tab
- [ ] `docs/opsera/deployment-matrix.md` or Google Drive matrix visible
- [ ] Optional: architecture diagram from LEARNING_PATH Step 1

---

## Minute 0–2 — Set the context

**Say:**

> "We're building hands-on experience with Opsera by implementing deployment pipelines for different app types. I'm starting with Python — our openIMIS claim module — using a **hybrid model**: GitHub Actions runs build and deploy commands; Opsera orchestrates the flow, security scans, quality gates, and approvals."

> "This matches what Kumar outlined: AWS and Azure paths, GitHub Actions, Opsera Job Engine, Checkmarx, and qTest."

**Show:** Hybrid diagram (from LEARNING_PATH.md)

---

## Minute 2–5 — Legacy app + why CI first (PY-01)

**Say:**

> "Before deploy, we need a reliable CI pipeline. PY-01 builds the Python package and runs the same quality gates we already use — flake8, mypy, Bandit, pip-audit, sibling compatibility."

**Show:** `.github/workflows/opsera-hybrid-python-ci.yml` (scroll key jobs only)

**Say:**

> "Opsera triggers this via `workflow_dispatch` and passes parameters like environment at runtime — dev, staging, or prod — without changing the YAML."

**Demo action:** Open Opsera → PY-01 → show step 1 (GitHub Actions) configuration

---

## Minute 5–8 — Run or replay CI

**Option A — Live run (if confident):**
- Trigger Opsera PY-01 with `environment=dev`
- Narrate Pipeline Activity as steps execute

**Option B — Replay (safer):**
- Open last green GHA run
- Walk through job steps: build → lint → mypy → bandit → artifact upload

**Say:**

> "Step 2 in the full design is Checkmarx through Opsera agents — we're wiring that next. Step 3 is qTest quality gate. For today I can show manual approval as a stand-in if qTest isn't linked yet."

**Show:** GHA Step Summary: "Opsera PY-01 CI Summary"

---

## Minute 8–11 — Deploy pattern preview (PY-02)

**Say:**

> "PY-02 is the same orchestration pattern for deployment. One pipeline, two cloud targets — AWS ECS or Azure Web App — selected by parameter `cloud_target`."

**Show:** `.github/workflows/opsera-hybrid-python-deploy.yml` inputs block

**Say:**

> "We always test with `dry_run=true` first — builds the Docker image but doesn't push to cloud. That's how we de-risk the demo and first dev deploy."

**Optional live:** Show dry_run GHA run logs ("Dry run: image built")

---

## Minute 11–13 — Matrix & team KB

**Say:**

> "I'm adding rows to our deployment matrix — Python done first, Java template ready, .NET and Informatica to expand. Each row captures observations and blockers so we build a team knowledge base."

**Show:** `docs/opsera/deployment-matrix.md` PY-01 / PY-02 rows

---

## Minute 13–15 — Learnings + next steps

**Say:**

> "What I've learned so far:"
> 1. Opsera doesn't replace GHA — it orchestrates it
> 2. Pipeline-level parameters let us pick environment and cloud at run time
> 3. Security and quality gates belong *between* CI and deploy, not after prod

> "Next steps: Checkmarx agent on PY-01, qTest linkage, first real AWS or Azure dev deploy with dry_run=false."

**Ask audience:**

> "Any preferences on AWS vs Azure for the first shared dev environment? Any existing Checkmarx project we should reuse?"

---

## Q&A cheat sheet

| Question | Short answer |
|----------|--------------|
| Why not only GitHub Actions? | Opsera adds Checkmarx, qTest, approvals, centralized deployment reporting |
| Is this production-ready? | Learning pipeline; dry_run and dev env first |
| What app is this? | openIMIS claim module — real Python codebase |
| Java / .NET? | Matrix template ready; same hybrid pattern |
| What if Checkmarx fails? | Triage with security; waivers per policy |
| Rollback? | Re-run deploy with previous image_tag / assembly pin |

---

## If something breaks during live demo

1. **Stay calm** — switch to recorded/screenshot backup
2. **Say:** "This is exactly why we're documenting blockers in the matrix"
3. **Show** last known green Pipeline Activity
4. **Offer** to follow up with logs after the session

---

## After demo

- [ ] Add Team observations to deployment-matrix.md
- [ ] Share GHA + Opsera run links in team channel
- [ ] Note blockers for next working session
