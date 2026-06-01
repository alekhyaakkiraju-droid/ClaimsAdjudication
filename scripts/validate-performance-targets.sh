#!/usr/bin/env bash
# WO-035: Performance validation preflight — documents targets and runs module smoke checks.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "==> WO-035 performance validation preflight"
echo "Targets: see docs/PERFORMANCE_VALIDATION.md and docs/BASELINE_BENCHMARK.md"

echo "==> Checking optimization modules import cleanly"
python - <<'PY'
import claim.read_queryset
import claim.submission_pipeline
import claim.query_cache
from claim.services.processing import process_claims_batch
from claim.services.report import ClaimReportService
print("optimization modules: OK")
PY

echo "==> Done. Run full S1–S5 benchmarks on openimis-be_py staging per BASELINE_BENCHMARK.md"
