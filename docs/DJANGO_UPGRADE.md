# Django 4.2 LTS upgrade (WO-009)

**Target:** Django **4.2.x** (LTS), Python **3.11+**

## Dependency constraint

`pyproject.toml`:

```toml
django>=4.2,<5
```

## Code changes in this module

| Area | Change |
|------|--------|
| `claim/__init__.py` | Removed deprecated `default_app_config` (auto-discovered via `ClaimConfig` in `apps.py`) |
| `claim/models.py` | `dispatch.Signal()` without `providing_args` (Django 4 compatible) |
| Translations | Already use `django.utils.translation.gettext` |

## Verification

- Assembly CI: `manage.py test claim` on Python 3.11 + PostgreSQL (fork module-only job).
- Local: from `openimis-be_py` with this module installed editable.

## Rollback

Pin `django>=3.2,<4` in `pyproject.toml` and restore `default_app_config` / `Signal(["claim"])` if required for emergency rollback.
