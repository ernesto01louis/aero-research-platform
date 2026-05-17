#!/usr/bin/env bash
# scripts/check_handoff_exists.sh
#
# Claude Code Stop-hook gate. Reads `.aero-stage` at repo root, then verifies
# that `docs/handoffs/STAGE-NN-*-DONE-*.md` exists with the required
# frontmatter fields populated. Exit 0 allows Stop; non-zero blocks it.
#
# Required frontmatter (per .claude/rules/handoff-discipline.md):
#   stage           — must match .aero-stage (zero-padded NN)
#   stage_name      — non-empty string
#   status          — one of {complete, partial, blocked}
#   date_completed  — non-empty ISO date (YYYY-MM-DD)
#   git_sha_end     — non-empty 40-char hex SHA
#
# Special case: if .aero-stage contains "01" AND no handoff exists yet AND
# the .aero-stage file was last modified less than 24 h ago, allow Stop with
# a warning. This avoids deadlocking the very first session before the
# template + handoff infrastructure is in place.
#
# Output:
#   stderr — human-readable reasoning; shown to the model on block
#   exit 0 — allow Stop
#   exit 2 — block Stop (Claude Code convention)

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [[ -z "$repo_root" ]]; then
  # Not in a git repo — likely running outside the project. Don't block.
  exit 0
fi

stage_file="$repo_root/.aero-stage"
if [[ ! -f "$stage_file" ]]; then
  echo "[handoff-gate] No .aero-stage file at $stage_file — not in an aero-research-platform tree. Allowing Stop." >&2
  exit 0
fi

stage="$(tr -d '[:space:]' < "$stage_file")"
if [[ ! "$stage" =~ ^[0-9]{2}$ ]]; then
  echo "[handoff-gate] .aero-stage content '$stage' is not a 2-digit number. Allowing Stop (something is malformed; fix .aero-stage)." >&2
  exit 0
fi

# Find handoff matching this stage
shopt -s nullglob
matches=("$repo_root/docs/handoffs/STAGE-${stage}-"*"-DONE-"*.md)
shopt -u nullglob

# Bootstrap escape hatch: stage 01, no handoff yet, .aero-stage recently created
if [[ ${#matches[@]} -eq 0 && "$stage" == "01" ]]; then
  if [[ $(( $(date +%s) - $(stat -c %Y "$stage_file") )) -lt 86400 ]]; then
    echo "[handoff-gate] Stage 01 bootstrap window (handoff infrastructure not yet committed). Allowing Stop with WARNING." >&2
    echo "[handoff-gate] Write docs/handoffs/STAGE-01-*-DONE-YYYY-MM-DD.md before tagging v0.0.1." >&2
    exit 0
  fi
fi

if [[ ${#matches[@]} -eq 0 ]]; then
  cat >&2 <<EOF
[handoff-gate] BLOCKED Stop.

No post-stage handoff found for stage $stage. Expected at:
  docs/handoffs/STAGE-${stage}-<slug>-DONE-YYYY-MM-DD.md

Write the handoff from docs/handoffs/_template.md before ending the
session. See .claude/rules/handoff-discipline.md for required
frontmatter and the 10 mandatory sections.

If you genuinely need to exit before the handoff is ready (rare —
e.g. blocked on operator input), commit a status:partial handoff
explaining what's blocked, then Stop.
EOF
  exit 2
fi

# At least one matching file. Validate frontmatter on the most recently
# modified one.
latest="$(ls -t "${matches[@]}" | head -n 1)"

extract_field() {
  # Extract YAML scalar field from the frontmatter block. Conservative
  # implementation that handles quoted and unquoted values.
  local field="$1"
  awk -v f="$field" '
    /^---[[:space:]]*$/ {
      n++
      if (n == 2) exit
      next
    }
    n == 1 && $0 ~ "^"f":" {
      val = $0
      sub("^"f":[[:space:]]*", "", val)
      gsub(/^["'\''[:space:]]+|["'\''[:space:]]+$/, "", val)
      print val
      exit
    }
  ' "$latest"
}

stage_field="$(extract_field stage || true)"
stage_name_field="$(extract_field stage_name || true)"
status_field="$(extract_field status || true)"
date_completed_field="$(extract_field date_completed || true)"
git_sha_end_field="$(extract_field git_sha_end || true)"

errors=()

# Normalize stage to two-digit form for comparison
normalized_stage="$(printf '%02d' "${stage_field:-0}" 2>/dev/null || echo "")"
if [[ "$normalized_stage" != "$stage" ]]; then
  errors+=("frontmatter 'stage' is '$stage_field'; expected '$stage' (from .aero-stage)")
fi
if [[ -z "$stage_name_field" ]]; then
  errors+=("frontmatter 'stage_name' is empty")
fi
if [[ ! "$status_field" =~ ^(complete|partial|blocked)$ ]]; then
  errors+=("frontmatter 'status' is '$status_field'; must be one of {complete, partial, blocked}")
fi
if [[ ! "$date_completed_field" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  errors+=("frontmatter 'date_completed' is '$date_completed_field'; must be YYYY-MM-DD")
fi
if [[ ! "$git_sha_end_field" =~ ^[0-9a-f]{40}$ ]]; then
  errors+=("frontmatter 'git_sha_end' is '$git_sha_end_field'; must be 40-char hex SHA")
fi

if [[ ${#errors[@]} -gt 0 ]]; then
  echo "[handoff-gate] BLOCKED Stop — handoff frontmatter incomplete at $latest" >&2
  for e in "${errors[@]}"; do
    echo "[handoff-gate]   - $e" >&2
  done
  echo "[handoff-gate] Fix the frontmatter and re-attempt Stop." >&2
  exit 2
fi

# All checks passed
echo "[handoff-gate] OK — Stage $stage handoff valid at $latest" >&2
exit 0
