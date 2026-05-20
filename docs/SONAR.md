# SonarCloud quality gate (ClaimsAdjudication)

**Project key:** `alekhyaakkiraju-droid_openimis-be-claim_py`  
**PR analysis:** SonarCloud GitHub App (~15s check: "SonarCloud Code Analysis")

## Common failures on this repo

| Rule | Meaning | Fix |
|------|---------|-----|
| `githubactions:S7630` | `${{ inputs.* }}` interpolated inside a `run:` shell block | Pass via `env:` (e.g. `DISPATCH_TAG: ${{ inputs.tag }}`) and use `$DISPATCH_TAG` in the script |
| `githubactions:S7637` | Action uses a version tag (`@v4`) instead of a full commit SHA | Pin `uses: org/action@<40-char-sha> # vX.Y.Z` |
| Security hotspot (quality gate) | Unreviewed hotspot on new code (often workflow files) | Resolve in Sonar UI or fix the workflow; do not blanket-exclude `.github` unless policy allows |

Workflow files under `.github/workflows/` are analyzed even when `sonar.sources=claim`. Hotspots on YAML count toward the **Quality Gate**.

## Before push / ship

```bash
./scripts/forge-pre-ship-sonar.sh
```

Run automatically from `./scripts/forge-wo-ship.sh` before `git push`.

## After a failed PR check

1. `gh pr checks <n> --repo alekhyaakkiraju-droid/ClaimsAdjudication | grep Sonar`
2. Open the PR link from the check summary (security hotspots / conditions).
3. Or query hotspots:

```bash
curl -s "https://sonarcloud.io/api/hotspots/search?projectKey=alekhyaakkiraju-droid_openimis-be-claim_py&pullRequest=<n>&status=TO_REVIEW"
```

## Pinning actions (S7637)

```yaml
# Bad
uses: gitleaks/gitleaks-action@v2.3.9

# Good
uses: gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7 # v2.3.9
```

Resolve SHA: `curl -s https://api.github.com/repos/<org>/<repo>/git/refs/tags/vX.Y.Z`

## `sonar-project.properties`

- `sonar.sources=claim` — Python only for main analysis
- `sonar.exclusions` — excludes tests/migrations; **does not** skip workflow security hotspots on PRs

Do not add `**/.github/**` to exclusions to hide real workflow issues; fix pins and input patterns instead.
