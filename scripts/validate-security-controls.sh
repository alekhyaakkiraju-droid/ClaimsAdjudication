#!/usr/bin/env bash
# WO-036: Security validation preflight — verify security modules and CI gate docs exist.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "==> WO-036 security validation preflight"

for mod in gql_authorization rest_authorization attachment_validation api_errors audit_governance; do
  python -c "import claim.${mod}; print('claim.${mod}: OK')"
done

test -f docs/SECURITY_VALIDATION.md
test -f docs/FORGE_CI_GATES.md
test -f .github/workflows/forge-quality-gates.yml

echo "==> Security modules and CI gate docs present"
