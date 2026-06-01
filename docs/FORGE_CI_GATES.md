# Forge CI quality gates (WO-007)

**Work order:** WO-007 — Adopt Forge CI gates  
**Project:** ClaimsAdjudication (`5fc679ab-b55c-441c-848d-2b5435a7462d`)

## Pipelines

| Workflow | When | Gates |
|----------|------|--------|
| [forge-quality-gates.yml](../.github/workflows/forge-quality-gates.yml) | PR, `develop`, `wo/**`, `feature/**` | Build, flake8, mypy, pip-audit, bandit (high), gitleaks |
| [ci.yml](../.github/workflows/ci.yml) → [ci_module.yml](../.github/workflows/ci_module.yml) | Same + assembly | Django tests, **60% critical-path coverage**, blocking flake8 |

## Gate details

### Fast module gates (`forge-quality-gates.yml`)

- **Build** — `python -m build` from `pyproject.toml`
- **Lint** — `flake8 claim` (blocking; ignores E501/W503 like assembly CI)
- **Type check** — `scripts/run-forge-mypy-gate.sh` (strict on public API modules; see [TYPE_ANNOTATIONS.md](TYPE_ANNOTATIONS.md))
- **Dependency scan** — `pip-audit` on `pyproject.toml` direct dependencies
- **SAST** — Bandit on `claim/` (high severity only)
- **Secret scan** — Gitleaks on full history

### Assembly CI (`ci_module.yml`)

- **Tests** — `manage.py test claim` (module-only on fork repos)
- **Coverage** — `coverage run` + `coverage report` with `.coveragerc` `fail_under = 60`
- **Flake8** — blocking (no longer `continue-on-error`)

## Local checks

```bash
python -m flake8 claim --config=.flake8 --ignore W503,E501
bash scripts/run-forge-mypy-gate.sh
python -m build
# Coverage (requires openimis-be_py):
OPENIMIS_MANAGE_PY=/path/to/openimis-be_py/openIMIS/manage.py ./scripts/check-critical-path-coverage.sh
```

## Release path

Failing any gate blocks merge. Production publish still uses [python-publish.yml](../.github/workflows/python-publish.yml) (WO-006).

## SonarCloud

PRs must pass **SonarCloud Code Analysis** (~15s). Workflow hotspots are common — see **[SONAR.md](SONAR.md)** and run `./scripts/forge-pre-ship-sonar.sh` before ship.
