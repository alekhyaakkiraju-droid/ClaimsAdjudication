#!/usr/bin/env bash
# Pre-ship SonarCloud guardrails for GitHub Actions workflows (ClaimsAdjudication).
# Catches githubactions:S7630 (inputs in run blocks) and S7637 (unpinned action tags).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

die() { echo "forge-pre-ship-sonar: $*" >&2; exit 1; }

[[ -d .github/workflows ]] || die "No .github/workflows directory"

errors=0

# Always validate S7630 on all workflows (small repo set).
for wf in .github/workflows/*.yml; do
  [[ -f "$wf" ]] || continue
  if ! python3 - "$wf" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
# Rough: any run block containing inputs interpolation
import re
for m in re.finditer(r"(?m)^(\s*)run:\s*\|?\s*$", text):
    start = m.end()
    indent = len(m.group(1))
    rest = text[start:]
    lines = rest.splitlines()
    block = []
    for line in lines:
        if line.strip() == "":
            block.append(line)
            continue
        cur_indent = len(line) - len(line.lstrip())
        if block and cur_indent <= indent and line.strip():
            break
        block.append(line)
    block_text = "\n".join(block)
    if "inputs." in block_text or "${{ inputs" in block_text:
        print(f"{path}: githubactions:S7630 — use env: for inputs, not run: interpolation")
        sys.exit(1)
sys.exit(0)
PY
  then
    errors=1
  fi
done

# S7637: pin check on workflows we edit (not vendored ci_module.yml unless touched).
PIN_CHECK=(
  .github/workflows/forge-quality-gates.yml
  .github/workflows/python-publish.yml
  .github/workflows/ci.yml
)
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  case "$f" in
    */ci_module.yml) continue ;;  # vendored upstream; Sonar hotspots target owned workflows
  esac
  PIN_CHECK+=("$f")
done < <(git diff --name-only origin/develop...HEAD -- '.github/workflows/*.yml' 2>/dev/null || true)

for wf in $(printf '%s\n' "${PIN_CHECK[@]}" | sort -u); do
  [[ -f "$wf" ]] || continue
  while IFS= read -r line; do
    [[ "$line" =~ uses: ]] || continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ @[0-9a-f]{40} ]] && continue
    if [[ "$line" =~ @v[0-9] ]] || [[ "$line" =~ @(main|master) ]]; then
      echo "$wf: githubactions:S7637 — pin to full commit SHA: $line"
      errors=1
    fi
  done < "$wf"
done

if [[ "$errors" -ne 0 ]]; then
  die "Fix workflow issues above before push (see docs/SONAR.md)"
fi

echo "forge-pre-ship-sonar: workflow checks passed (S7630, S7637 on owned/changed workflows)"
