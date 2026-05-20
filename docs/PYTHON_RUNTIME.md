# Python runtime (WO-008)

**Target:** Python **3.11+** (CI and packaging use **3.11**).

## Metadata

- `pyproject.toml`: `requires-python = ">=3.11"`
- Trove classifiers: 3.11, 3.12 only (EOL 3.6–3.10 removed from advertised support)
- Release workflow: `python-version: "3.11"` in `.github/workflows/python-publish.yml`
- Module CI: `actions/setup-python` **3.11** in `.github/workflows/ci_module.yml`

## Verification

Assembly CI runs `manage.py test claim` on Python 3.11 with PostgreSQL (fork: module-only suite).
