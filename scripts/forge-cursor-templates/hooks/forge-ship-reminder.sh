#!/bin/bash
# After agent stop: nudge ship flow when on a WO branch with unpushed commits or no PR yet.
# Never blocks; only adds context when conditions match.
#
# Suppressed when: FORGE_WO_SHIPPED=1, recent .forge/last-ship-mcp.json for this WO/branch,
# or an open PR exists on origin for the current branch.

input=$(cat)
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BRANCH="$(git branch --show-current 2>/dev/null || true)"

if ! echo "$BRANCH" | grep -qE '^wo/WO-[0-9]+'; then
  exit 0
fi

WO="$(echo "$BRANCH" | sed -E 's#^wo/(WO-[0-9]+).*#\1#')"

# Session / env override
if [[ "${FORGE_WO_SHIPPED:-}" == "1" ]]; then
  exit 0
fi

# Recent ship marker from forge-wo-ship.sh
MCP_FILE="$ROOT/.forge/last-ship-mcp.json"
if [[ -f "$MCP_FILE" ]] && command -v jq >/dev/null 2>&1; then
  MCP_WO="$(jq -r '.wo_label // empty' "$MCP_FILE" 2>/dev/null || true)"
  MCP_BRANCH="$(jq -r '
    .create_pull_request.branch_name //
    .update_work_order.branch_name //
    empty
  ' "$MCP_FILE" 2>/dev/null || true)"
  if [[ "$MCP_WO" == "$WO" && "$MCP_BRANCH" == "$BRANCH" ]]; then
    SHIPPED_AT="$(jq -r '.shipped_at // empty' "$MCP_FILE" 2>/dev/null || true)"
    RECENT=0
    if [[ -n "$SHIPPED_AT" ]]; then
      SHIPPED_EPOCH="$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$SHIPPED_AT" +%s 2>/dev/null \
        || date -d "$SHIPPED_AT" +%s 2>/dev/null || echo 0)"
      NOW_EPOCH="$(date +%s)"
      if [[ "$SHIPPED_EPOCH" -gt 0 && $((NOW_EPOCH - SHIPPED_EPOCH)) -lt 604800 ]]; then
        RECENT=1
      fi
    else
      # Fallback: file mtime within 7 days
      if [[ "$(uname -s)" == "Darwin" ]]; then
        MTIME="$(stat -f %m "$MCP_FILE" 2>/dev/null || echo 0)"
      else
        MTIME="$(stat -c %Y "$MCP_FILE" 2>/dev/null || echo 0)"
      fi
      NOW_EPOCH="$(date +%s)"
      if [[ "$MTIME" -gt 0 && $((NOW_EPOCH - MTIME)) -lt 604800 ]]; then
        RECENT=1
      fi
    fi
    [[ "$RECENT" == "1" ]] && exit 0
  fi
fi

# PR already open on fork for this branch (GH_REPO = origin, not upstream)
_gh_repo() {
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"
  echo "$url" | sed -E 's#.*github\.com[:/]([^/]+/[^/.]+).*#\1#; s#\.git$##'
}
_has_pr_for_branch() {
  command -v gh >/dev/null 2>&1 || return 1
  local repo
  repo="$(_gh_repo)"
  [[ -n "$repo" ]] || return 1
  GH_REPO="$repo" gh pr list --head "$BRANCH" --state open --json number --limit 1 2>/dev/null \
    | grep -q '"number"'
}
if _has_pr_for_branch; then
  exit 0
fi

NEEDS=""

if git rev-parse '@{u}' >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
  [[ "$AHEAD" != "0" ]] && NEEDS="push"
else
  NEEDS="push"
fi

if ! _has_pr_for_branch; then
  NEEDS="${NEEDS:+$NEEDS, }open PR"
fi

[[ -n "$NEEDS" ]] || exit 0

cat <<EOF
{"followup_message":"WO ship reminder ($WO): run \`./scripts/forge-wo-ship.sh $WO <work_order_uuid>\` then Forge MCP \`create_pull_request\` + \`update_work_order\` (status in_review). See docs/FORGE_WO_WORKFLOW.md."}
EOF
exit 0
