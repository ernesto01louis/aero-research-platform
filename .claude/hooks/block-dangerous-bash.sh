#!/usr/bin/env bash
# .claude/hooks/block-dangerous-bash.sh
#
# PreToolUse hook for Bash. Reads the tool input from stdin (JSON), inspects
# the command field for patterns that the permission allow/deny list cannot
# catch via simple prefix match, and blocks with a clear error if any match.
#
# Returns:
#   exit 0 — allow the command
#   exit 2 — block; stderr is shown to the model
#
# Patterns blocked:
#   * SQL `DROP TABLE` / `DROP DATABASE` / `DROP ROLE` (any case)
#     — Stage 04 hits this when configuring Postgres on LXC 202; the rule is
#     "never drop existing non-aero objects". Aero-namespaced drops still
#     need explicit `approved` per the project brief.
#   * `git push --force-with-lease` is also blocked (still rewrites history;
#     use `git revert` instead)
#   * `--no-verify` flag on git commit/push (Hard Rule 6)
#   * `--dangerously-skip-permissions` (Hard Rule 6)
#   * `--allow-dirty` on aero CLI without `git_sha=*-dirty` in MLflow
#     (placeholder; full enforcement in Stage 04)
#
# This script is a defense-in-depth layer; the permission allowlist in
# settings.json is the first line.

set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

if [[ -z "$cmd" ]]; then
  exit 0
fi

block() {
  echo "BLOCKED by .claude/hooks/block-dangerous-bash.sh: $1" >&2
  echo "Command: $cmd" >&2
  exit 2
}

# Case-insensitive matches for SQL destructive ops
shopt -s nocasematch
if [[ "$cmd" =~ (drop[[:space:]]+(table|database|role|schema)) ]]; then
  block "SQL DROP detected. Per Stage-04 propose-first policy, all DROP ops on existing Postgres objects require explicit operator 'approved'."
fi
shopt -u nocasematch

# Git history-rewriting
if [[ "$cmd" =~ (git[[:space:]]+push[[:space:]].*--force-with-lease) ]]; then
  block "git push --force-with-lease still rewrites history. Use git revert."
fi

# Skip-verification flags
if [[ "$cmd" =~ --no-verify ]]; then
  block "--no-verify violates Hard Rule 6 (pre-commit hooks are not optional). If a hook is wrong, fix the hook."
fi

if [[ "$cmd" =~ --dangerously-skip-permissions ]]; then
  block "--dangerously-skip-permissions is forbidden outside ephemeral containers (Hard Rule 6)."
fi

exit 0
