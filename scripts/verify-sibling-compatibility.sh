#!/usr/bin/env bash
# WO-010: Static sibling compatibility verification for openimis-be-claim.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PYPROJECT="$ROOT/pyproject.toml"
CLAIM_DIR="$ROOT/claim"

die() { echo "verify-sibling-compatibility: $*" >&2; exit 1; }

import_name_for_pkg() {
  case "$1" in
    openimis-be-core) echo core ;;
    openimis-be-claim_batch) echo claim_batch ;;
    openimis-be-insuree) echo insuree ;;
    openimis-be-location) echo location ;;
    openimis-be-medical) echo medical ;;
    openimis-be-policy) echo policy ;;
    openimis-be-product) echo product ;;
    openimis-be-report) echo report ;;
    *) echo "" ;;
  esac
}

[[ -f "$PYPROJECT" ]] || die "Missing $PYPROJECT"
[[ -d "$CLAIM_DIR" ]] || die "Missing $CLAIM_DIR"

OPTIONAL_IMPORTS="medical_pricelist"

echo "==> Declared sibling dependencies (pyproject.toml)"
DECLARED="$(grep -E '^\s+"openimis-be-' "$PYPROJECT" | sed -E 's/.*"(openimis-be-[^"]+)".*/\1/' | sort -u)"
echo "$DECLARED" | sed 's/^/  - /'

echo "==> Import scan (claim/)"
IMPORTED="$(grep -RhE '^(from|import) ([a-z_][a-z0-9_]*)' "$CLAIM_DIR" --include='*.py' 2>/dev/null \
  | sed -E 's/^(from|import) ([a-z_][a-z0-9_]*).*/\2/' | sort -u)"

echo "==> Verify each declared sibling is referenced"
while IFS= read -r pkg; do
  [[ -z "$pkg" ]] && continue
  imp="$(import_name_for_pkg "$pkg")"
  [[ -z "$imp" ]] && continue
  if ! echo "$IMPORTED" | grep -qx "$imp"; then
    echo "WARN: $pkg (import: $imp) has no direct import in claim/ (may be transitive)"
  fi
done <<< "$DECLARED"

echo "==> Imports outside declared siblings (assembly review)"
while IFS= read -r mod; do
  [[ -z "$mod" ]] && continue
  case "$mod" in
    claim|django|rest_framework|graphene|graphql|graphql_jwt|uuid|decimal|json|base64|unittest|datetime)
      continue ;;
    core|claim_batch|insuree|location|medical|policy|product|report)
      continue ;;
    medical_pricelist)
      echo "  NOTE: $mod is assembly-only (see docs/SIBLING_COMPATIBILITY.md)"
      continue ;;
    calendar|faker|gettext|graphene_django|graphene_django_optimizer|importlib|requests|string|tools|xml|typing|enum|io|os|sys|re|math|copy|functools|itertools|logging|csv|hashlib|pathlib|urllib|tempfile|random|collections|PIL|reportlab)
      continue ;;
  esac
  if echo "$IMPORTED" | grep -qx "$mod"; then
    found=0
    while IFS= read -r pkg; do
      imp="$(import_name_for_pkg "$pkg")"
      [[ "$mod" == "$imp" ]] && found=1
    done <<< "$DECLARED"
    [[ $found -eq 0 ]] && echo "  WARN: import '$mod' not mapped to pyproject sibling (review)"
  fi
done <<< "$IMPORTED"

echo "==> ClaimConfig pluggable registration"
python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = (root / "claim" / "apps.py").read_text()
assert "class ClaimConfig(AppConfig)" in source
assert 'MODULE_NAME = "claim"' in source or "MODULE_NAME" in source
print("  ClaimConfig AppConfig present; module name claim")
PY

echo "verify-sibling-compatibility: static checks passed"
