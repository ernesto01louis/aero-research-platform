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
#   * SQL `DROP TABLE` / `DROP DATABASE` / `DROP ROLE` / `DROP SCHEMA`
#   * `git push --force-with-lease` (still rewrites history)
#   * `--no-verify` / `--dangerously-skip-permissions` (Hard Rule 6)
#   * Stage 02: `pct destroy|stop` / `qm destroy|stop` even inside compound
#     commands (the permissions deny-list only prefix-matches)
#   * Stage 02: file-level writes to protected host config — `/etc/pve/`,
#     `/etc/network/interfaces`, `/etc/subuid`, `/etc/subgid` (Hard Rule 5;
#     use the Proxmox API — pvesh/pct/qm — instead of editing these by hand)
#   * Stage 02: SSH to a shared non-aero host (TrueNAS / Postgres / Grafana)
#     carrying a destructive verb — those services are read-only to the aero
#     stack (Hard Rule 11). Aero LXC aliases are unrestricted.
#
# Defense-in-depth layer; the permission allowlist in settings.json is first.

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

# --- SQL destructive ops (case-insensitive) ---
shopt -s nocasematch
if [[ "$cmd" =~ (drop[[:space:]]+(table|database|role|schema)) ]]; then
  block "SQL DROP detected. Per Stage-04 propose-first policy, all DROP ops on existing Postgres objects require explicit operator 'approved'."
fi
shopt -u nocasematch

# --- Git history-rewriting ---
if [[ "$cmd" =~ (git[[:space:]]+push[[:space:]].*--force-with-lease) ]]; then
  block "git push --force-with-lease still rewrites history. Use git revert."
fi

# --- Skip-verification flags ---
if [[ "$cmd" =~ --no-verify ]]; then
  block "--no-verify violates Hard Rule 6 (pre-commit hooks are not optional). If a hook is wrong, fix the hook."
fi

if [[ "$cmd" =~ --dangerously-skip-permissions ]]; then
  block "--dangerously-skip-permissions is forbidden outside ephemeral containers (Hard Rule 6)."
fi

# --- Destructive Proxmox guest operations (compound-command safe) ---
shopt -s nocasematch
if [[ "$cmd" =~ (^|[^[:alnum:]_/])pct[[:space:]]+(destroy|stop)([^[:alnum:]]|$) ]]; then
  block "pct destroy/stop is forbidden. Aero LXCs use 'pct reboot'/'pct shutdown'; never stop or destroy a guest (Hard Rule 11)."
fi
if [[ "$cmd" =~ (^|[^[:alnum:]_/])qm[[:space:]]+(destroy|stop)([^[:alnum:]]|$) ]]; then
  block "qm destroy/stop is forbidden — VMs are pre-existing non-aero infrastructure (Hard Rule 11)."
fi
shopt -u nocasematch

# --- File-level writes to protected host configuration ---
protected='/etc/pve/|/etc/network/interfaces|/etc/subuid|/etc/subgid'
if [[ "$cmd" =~ ($protected) ]]; then
  if [[ "$cmd" =~ (\>|sed[[:space:]]+-i|(^|[[:space:]])(tee|truncate)[[:space:]]) ]]; then
    block "File-level write to a protected host path ($protected) requires explicit operator 'approved' (Hard Rule 5). Change Proxmox config via the API (pvesh/pct/qm/pvesm), not by editing these files."
  fi
fi

# --- SSH to shared non-aero hosts must stay read-only ---
if [[ "$cmd" =~ (^|[^[:alnum:]_])ssh[[:space:]] ]]; then
  shared='truenas|postgres-server|grafana-server|192\.168\.2\.100|192\.168\.2\.184|192\.168\.2\.188'
  if [[ "$cmd" =~ ($shared) ]]; then
    shopt -s nocasematch
    if [[ "$cmd" =~ ((^|[[:space:]])rm[[:space:]]|mkfs|(^|[[:space:]])dd[[:space:]]|systemctl[[:space:]]+(stop|restart|disable|mask)|apt(-get)?[[:space:]]+(install|remove|purge|upgrade)|drop[[:space:]]+(table|database)|pct[[:space:]]+(destroy|stop)|qm[[:space:]]+(destroy|stop)) ]]; then
      block "SSH to a shared non-aero host carrying a destructive verb. The shared services (TrueNAS/Postgres/Grafana) are read-only to the aero stack (Hard Rule 11)."
    fi
    shopt -u nocasematch
  fi
fi

exit 0
