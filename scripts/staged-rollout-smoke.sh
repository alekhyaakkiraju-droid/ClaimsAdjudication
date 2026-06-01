#!/usr/bin/env bash
# WO-038: Staged rollout smoke — run preflight scripts and verify release docs exist.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "==> WO-038 staged rollout smoke"

bash scripts/validate-security-controls.sh
bash scripts/validate-performance-targets.sh

for doc in STAGED_ROLLOUT.md ROLLBACK_RUNBOOK.md RELEASE.md API_CONTRACTS.md; do
  test -f "docs/$doc" && echo "docs/$doc: OK"
done

python -m build >/dev/null
echo "==> Package builds successfully — ready for release candidate tagging"
