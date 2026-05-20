# Sibling module compatibility (WO-010)

The claim module is a **pluggable** openIMIS backend component installed via [openimis-be_py](https://github.com/openimis/openimis-be_py). Runtime and Django upgrades (WO-008/009) must remain compatible with required sibling modules.

## Required sibling modules

| PyPI / assembly package | Django app | Interfaces used by claim |
|-------------------------|------------|---------------------------|
| `openimis-be-core` | `core` | `VersionedModel`, `ModuleConfiguration`, GraphQL base types, `MutationLog`, permissions, `TimeUtils`, signals |
| `openimis-be-insuree` | `insuree` | `Insuree` FK, GraphQL `InsureeGQLType`, test helpers |
| `openimis-be-location` | `location` | `HealthFacility`, `Location`, `LocationManager`, schema types |
| `openimis-be-medical` | `medical` | `Item`, `Service`, `Diagnosis`, pricelist links |
| `openimis-be-policy` | `policy` | `Policy`, coverage validation |
| `openimis-be-product` | `product` | `Product`, `ProductItem`, `ProductService` |
| `openimis-be-claim_batch` | `claim_batch` | `BatchRun` GraphQL type |
| `openimis-be-report` | `report` | `ReportService` for claim printing |

### Assembly-only dependency

| Package | App | Notes |
|---------|-----|-------|
| `openimis-be-medical_pricelist` | `medical_pricelist` | Used in `claim/validations.py` and tests; **not** listed in `pyproject.toml` — must be present in host `openimis.json` / assembly requirements. No breaking change observed post WO-009. |

## Verification plan

| Step | Tool | Evidence |
|------|------|----------|
| 1. Static dependency ↔ import alignment | `./scripts/verify-sibling-compatibility.sh` | CI job **Sibling compatibility (static)** in `forge-quality-gates.yml` |
| 2. Pluggable app registration | Same script + `claim/tests/test_sibling_integration.py` | `ClaimConfig` / `MODULE_NAME=claim` |
| 3. Runtime integration (assembly) | Default CI `manage.py test claim` | PostgreSQL module + full assembly jobs on PR |
| 4. Critical path cross-module flows | `claim/tests/test_critical_paths.py`, `test_workflows.py` | Create/submit/query/attachment/report paths |

## Execution evidence (post WO-008/009)

- **Python 3.11+** and **Django 4.2** constraints in `pyproject.toml`.
- **Module CI** exercises claim with sibling test helpers (`core`, `insuree`, `medical`, `policy`, `product`, `location`).
- **No blocking compatibility defects** found in this repository after the runtime/framework upgrade; sibling repos are unchanged per WO scope.

## Compatibility issues and coordination

| Issue | Impact | Remediation / coordination |
|-------|--------|----------------------------|
| `medical_pricelist` not in `pyproject.toml` | Host assembly must include module for validation/pricelist tests | Document in assembly `openimis.json`; optional future WO to add explicit dependency if published to PyPI |
| Sibling Django 4.2 alignment | Claim assumes siblings support Django 4.2 in assembled backend | Coordinate with openIMIS release train; verify assembly image pins compatible sibling tags |
| `openimis-be-*` unpinned in metadata | Versions resolved at assembly install time | Release manager pins versions in `openimis-be_py` requirements for reproducible deployments |

## Local checks

```bash
./scripts/verify-sibling-compatibility.sh
python -m flake8 claim --config=.flake8 --ignore W503,E501
./scripts/forge-pre-ship-sonar.sh
```

Full integration (requires assembly):

```bash
export OPENIMIS_MANAGE_PY=/path/to/openimis-be_py/openIMIS/manage.py
./scripts/check-critical-path-coverage.sh
```

## Rollback

If a sibling regression is detected in assembly only, pin this module to the last known-good tag and file a coordination ticket against the affected sibling module; do not patch sibling code from this repository unless explicitly scoped.
