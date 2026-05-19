#!/usr/bin/env bash
# Run critical-path coverage for the claim module (WO-004).
# Requires openimis-be_py: set OPENIMIS_MANAGE_PY to manage.py path.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
RCFILE="$ROOT/.coveragerc"
MANAGE="${OPENIMIS_MANAGE_PY:-}"

die() { echo "check-critical-path-coverage: $*" >&2; exit 1; }

[[ -f "$RCFILE" ]] || die "Missing $RCFILE"
command -v coverage >/dev/null 2>&1 || die "pip install coverage"

if [[ -z "$MANAGE" ]]; then
  die "Set OPENIMIS_MANAGE_PY to openimis-be_py/openIMIS/manage.py"
fi
[[ -f "$MANAGE" ]] || die "manage.py not found: $MANAGE"

MANAGE_DIR="$(cd "$(dirname "$MANAGE")" && pwd)"
echo "==> coverage run (claim module, critical paths)"
(
  cd "$MANAGE_DIR"
  coverage run --rcfile="$RCFILE" "$(basename "$MANAGE")" test claim
)
echo "==> coverage report (fail_under=60)"
coverage report --rcfile="$RCFILE"
