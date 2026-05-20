#!/usr/bin/env bash
# WO-007: Run mypy with project baseline config (see pyproject.toml [tool.mypy]).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
python -m mypy claim --config-file=pyproject.toml
