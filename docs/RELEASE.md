# Release workflow

Publishing uses [`.github/workflows/python-publish.yml`](../.github/workflows/python-publish.yml) and PEP 621 packaging in `pyproject.toml`.

## Version from Git tag

On release, the workflow writes the tag (without a leading `v`) into `VERSION`. `pyproject.toml` reads that file via `[tool.setuptools.dynamic] version = { file = "VERSION" }`.

The legacy `setup.py` `sed` version injection is **not** used.

## Test a release build (no PyPI upload)

1. Open **Actions → Upload Python Package → Run workflow**.
2. Set **tag** (e.g. `v1.4.1`) and leave **dry_run** enabled.
3. Confirm the job passes **Verify package version matches tag**.

## Production release

1. Merge changes to `develop`.
2. Create a GitHub **Release** with tag `vX.Y.Z` (workflow runs on `release: created`).
3. Confirm the published wheel/sdist version on PyPI matches the tag.
