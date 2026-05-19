#!/usr/bin/env bash
# scripts/run_long.sh
#
# Canonical long-running-job pattern for the aero platform. Submits a command
# to an aero LXC inside a detached tmux session, returns immediately, and drops
# .done / .failed sentinels so callers poll instead of holding a connection
# open. This is the pattern every later stage uses to launch CFD / training
# jobs that outlast a single Claude Code turn.
#
# Submit:  run_long.sh <aero-alias> <session-name> <command...>
# Status:  run_long.sh status <aero-alias> <session-name>
# Wait:    run_long.sh wait   <aero-alias> <session-name> [timeout-seconds]
# Logs:    run_long.sh logs   <aero-alias> <session-name>
# List:    run_long.sh list   <aero-alias>
#
# Remote job state lives in ~/.aero-jobs/<session-name>/ on the target LXC:
#   cmd.sh      — the submitted command
#   output.log  — combined stdout + stderr
#   rc          — exit code, written on completion
#   .done       — sentinel; present iff the job exited 0
#   .failed     — sentinel; present iff the job exited non-zero
#
# Exit codes for `status` / `wait`: 0 done, 1 failed, 2 running/timeout,
# 3 unknown.

set -euo pipefail

AERO_ALIASES=(aero-build aero-dev aero-mlflow aero-vv aero-prefect aero-agent aero-lit)
JOBROOT=".aero-jobs"   # relative to the remote user's home directory

die() { echo "run_long: $*" >&2; exit 64; }

is_alias() {
  local a
  for a in "${AERO_ALIASES[@]}"; do [[ "$a" == "$1" ]] && return 0; done
  return 1
}

usage() {
  grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

cmd_submit() {
  local alias=$1 session=$2
  shift 2
  is_alias "$alias" || die "unknown aero alias '$alias' (expected: ${AERO_ALIASES[*]})"
  [[ -n $session ]] || die "session name required"
  [[ $session =~ ^[A-Za-z0-9._-]+$ ]] || die "session name must match [A-Za-z0-9._-]+"
  [[ $# -gt 0 ]] || die "command required"
  local command="$*"
  local jobdir="$JOBROOT/$session"

  if ssh "$alias" "tmux has-session -t '$session' 2>/dev/null"; then
    die "session '$session' already running on $alias — pick another name"
  fi

  ssh "$alias" "mkdir -p '$jobdir' && rm -f '$jobdir/.done' '$jobdir/.failed' '$jobdir/rc'"
  printf '%s\n' "$command" | ssh "$alias" "cat > '$jobdir/cmd.sh'"

  # Fixed wrapper: run cmd.sh, capture rc, drop the matching sentinel.
  ssh "$alias" "cat > '$jobdir/run.sh'" <<WRAP
#!/usr/bin/env bash
cd "\$HOME"
bash "$jobdir/cmd.sh" > "$jobdir/output.log" 2>&1
rc=\$?
echo "\$rc" > "$jobdir/rc"
if [ "\$rc" -eq 0 ]; then touch "$jobdir/.done"; else touch "$jobdir/.failed"; fi
WRAP

  ssh "$alias" "tmux new-session -d -s '$session' \"bash '$jobdir/run.sh'\""
  echo "submitted '$session' on $alias (job dir: ~/$jobdir)"
  echo "  status: $0 status $alias $session"
  echo "  wait:   $0 wait   $alias $session"
  echo "  logs:   $0 logs   $alias $session"
}

remote_state() {
  local alias=$1 session=$2
  ssh "$alias" "
    if   [ -f '$JOBROOT/$session/.done' ];   then echo done
    elif [ -f '$JOBROOT/$session/.failed' ]; then echo failed
    elif tmux has-session -t '$session' 2>/dev/null; then echo running
    else echo unknown; fi"
}

cmd_status() {
  local alias=$1 session=$2
  is_alias "$alias" || die "unknown aero alias '$alias'"
  local state
  state=$(remote_state "$alias" "$session")
  echo "$session@$alias: $state"
  case $state in
    done) return 0 ;; failed) return 1 ;; running) return 2 ;; *) return 3 ;;
  esac
}

cmd_wait() {
  local alias=$1 session=$2 timeout=${3:-3600}
  is_alias "$alias" || die "unknown aero alias '$alias'"
  local elapsed=0 interval=5 state
  while true; do
    state=$(remote_state "$alias" "$session")
    case $state in
      done)   echo "$session@$alias: done";   return 0 ;;
      failed) echo "$session@$alias: failed (see: $0 logs $alias $session)"; return 1 ;;
    esac
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "$session@$alias: still running after ${timeout}s (timeout)" >&2
      return 2
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
}

cmd_logs() {
  local alias=$1 session=$2
  is_alias "$alias" || die "unknown aero alias '$alias'"
  ssh "$alias" "cat '$JOBROOT/$session/output.log' 2>/dev/null" \
    || die "no output log for '$session' on $alias"
}

cmd_list() {
  local alias=$1
  is_alias "$alias" || die "unknown aero alias '$alias'"
  echo "tmux sessions on $alias:"
  ssh "$alias" "tmux list-sessions 2>/dev/null || echo '  (none)'"
}

[[ $# -ge 1 ]] || usage 1
case "$1" in
  status) shift; [[ $# -eq 2 ]] || die "usage: run_long.sh status <alias> <session>"; cmd_status "$@" ;;
  wait)   shift; [[ $# -ge 2 ]] || die "usage: run_long.sh wait <alias> <session> [timeout]"; cmd_wait "$@" ;;
  logs)   shift; [[ $# -eq 2 ]] || die "usage: run_long.sh logs <alias> <session>"; cmd_logs "$@" ;;
  list)   shift; [[ $# -eq 1 ]] || die "usage: run_long.sh list <alias>"; cmd_list "$@" ;;
  -h | --help) usage 0 ;;
  *) cmd_submit "$@" ;;
esac
