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
# Kill:    run_long.sh kill   <aero-alias> <session-name>
#
# <aero-alias> accepts an optional SSH user prefix (e.g. root@aero-build) to
# run the job as that user — Stage 03 onward, solver SIFs run as the LXC root.
#
# Remote job state lives in ~/.aero-jobs/<session-name>/ on the target LXC:
#   cmd.sh      — the submitted command
#   output.log  — combined stdout + stderr
#   rc          — exit code, written on completion
#   .done       — sentinel; present iff the job exited 0
#   .failed     — sentinel; present iff the job exited non-zero
#
# Exit codes for `status` / `wait`: 0 done, 1 failed, 2 running/timeout,
# 3 unknown, 4 vanished.
#
# `vanished` (Stage 19) is a TERMINAL state: no sentinel was ever written, no
# `rc` exists, and the tmux session is gone. The job did not finish — it was
# killed, or the tmux server died under it. Before this state existed,
# `remote_state` reported such a job as `unknown` and `wait` fell through to its
# timeout branch, so a job killed at minute 5 of a 6-hour wait blocked the caller
# for the full six hours and was then reported as "still running". A dead solve
# must be distinguishable from a slow one; that is what gate K2 means by
# `participant-died` being a loud failure. A grace window (VANISH_GRACE_MIN)
# keeps the submit→tmux-registration race from being misread as a death.
#
# AERO_RUN_LONG_REAP=1 makes `wait` the OWNER of the job's lifetime: on timeout,
# and on SIGTERM/SIGINT/SIGHUP, it kills the remote tmux session instead of
# leaving it detached. CI sets this. It is OPT-IN precisely because the default
# ("give up watching, leave the job running") is the right semantic for a human
# who submits a solve and stops watching it — but it is the wrong one for a CI
# job, where a cancelled or timed-out step abandons its solves forever. That
# asymmetry is what accumulated 2690 job directories and 31 GB of dead solver
# logs on aero-build between 2026-07-05 and 2026-07-28, and what left detached
# root tmux solves competing for the V&V runner's cores.

set -euo pipefail

AERO_ALIASES=(aero-build aero-dev aero-mlflow aero-vv aero-prefect aero-agent aero-lit)
JOBROOT=".aero-jobs"   # relative to the remote user's home directory
VANISH_GRACE_MIN=1     # a job dir younger than this is "starting", never "vanished"
REAP=${AERO_RUN_LONG_REAP:-0}   # 1 ⇒ `wait` owns the job's lifetime (see header)

die() { echo "run_long: $*" >&2; exit 64; }

is_alias() {
  # Accept a bare alias or a [user@]alias target (e.g. root@aero-build) and
  # validate the alias part, ignoring any user@ prefix. Added Stage 03: solver
  # SIFs must run as the LXC root (non-root apptainer exec fails in the
  # unprivileged LXC), so jobs are submitted to root@aero-build.
  local a bare="${1##*@}"
  for a in "${AERO_ALIASES[@]}"; do [[ "$a" == "$bare" ]] && return 0; done
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

  # FAIL-LOUD on an unreachable host. `if ssh ...` swallows a connection failure
  # as "no such session" and submits anyway, which is the opposite of what the
  # guard is for: it would double-submit onto a host we cannot see.
  local dup
  dup=$(ssh "$alias" "tmux has-session -t '$session' 2>/dev/null && echo yes || echo no") \
    || die "cannot reach $alias to check for a duplicate session — refusing to submit"
  [[ $dup == no ]] || die "session '$session' already running on $alias — pick another name"

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
  # Order is load-bearing: the two sentinels are terminal and authoritative, so
  # they are checked before the tmux session (a job that finished microseconds
  # ago may still have a session lingering). `vanished` is only reachable once
  # the job dir has aged past the grace window, so the submit→tmux race cannot
  # be misreported as a death.
  local alias=$1 session=$2
  ssh "$alias" "
    if   [ -f '$JOBROOT/$session/.done' ];   then echo done
    elif [ -f '$JOBROOT/$session/.failed' ]; then echo failed
    elif tmux has-session -t '$session' 2>/dev/null; then echo running
    elif [ ! -d '$JOBROOT/$session' ]; then echo unknown
    elif [ -n \"\$(find '$JOBROOT/$session' -maxdepth 1 -name cmd.sh -mmin +$VANISH_GRACE_MIN 2>/dev/null)\" ]; then echo vanished
    else echo running; fi"
}

cmd_kill() {
  # Terminate a detached job and leave an HONEST record: a killed job gets the
  # .failed sentinel and rc=143, so a later `status` reports `failed` rather
  # than `vanished`. Idempotent — killing an already-finished job never
  # overwrites its real sentinel.
  local alias=$1 session=$2
  is_alias "$alias" || die "unknown aero alias '$alias'"
  ssh "$alias" "
    tmux kill-session -t '$session' 2>/dev/null || true
    if [ -d '$JOBROOT/$session' ] \
       && [ ! -f '$JOBROOT/$session/.done' ] \
       && [ ! -f '$JOBROOT/$session/.failed' ]; then
      echo 143 > '$JOBROOT/$session/rc'
      touch '$JOBROOT/$session/.failed'
    fi" || true
  echo "$session@$alias: killed (recorded as failed, rc=143)"
}

cmd_status() {
  local alias=$1 session=$2
  is_alias "$alias" || die "unknown aero alias '$alias'"
  local state
  state=$(remote_state "$alias" "$session")
  echo "$session@$alias: $state"
  case $state in
    done) return 0 ;; failed) return 1 ;; running) return 2 ;;
    vanished) return 4 ;; *) return 3 ;;
  esac
}

cmd_wait() {
  local alias=$1 session=$2 timeout=${3:-3600}
  is_alias "$alias" || die "unknown aero alias '$alias'"
  # Elapsed time is read from a REAL clock, not accumulated as `elapsed += interval`.
  # Each loop also pays for `remote_state`'s SSH round trip (~0.3-1 s), so counting
  # only the sleeps made this ceiling run ~10 % slow: a nominal 4 h wait did not fire
  # until ~4 h 24 m. LocalSSHExecutor guards the subprocess at `timeout_s + 120`
  # (4 h 02 m), so the guard always won the race, SIGKILLed this script before it
  # reached the reap branch below, and AERO_RUN_LONG_REAP=1 became decorative on
  # exactly the path it was written for. Diagnosed from moving-vv run 30615205786,
  # which died at 4 h 02 m 32 s and left pimpleFoam running on aero-dev.
  local start_epoch elapsed interval=5 state
  start_epoch=$(date +%s)

  # When this waiter owns the job's lifetime, a signal must take the remote job
  # down with it. Without this, cancelling the CI step that runs the V&V suite
  # left its solves detached and running — the runner reports `busy` with no job
  # in flight, and the next run competes with the corpses of the last one.
  if [ "$REAP" = "1" ]; then
    trap 'echo "run_long: signalled — reaping ${session}@${alias}" >&2; cmd_kill "$alias" "$session" || true; exit 2' TERM INT HUP
  fi

  while true; do
    state=$(remote_state "$alias" "$session")
    case $state in
      done)   echo "$session@$alias: done";   return 0 ;;
      failed) echo "$session@$alias: failed (see: $0 logs $alias $session)"; return 1 ;;
      vanished)
        echo "$session@$alias: VANISHED — tmux session gone, no sentinel, no rc." >&2
        echo "  The job did NOT complete; it was killed or its tmux server died." >&2
        echo "  Logs (may be partial): $0 logs $alias $session" >&2
        return 4 ;;
    esac
    elapsed=$(( $(date +%s) - start_epoch ))
    if [ "$elapsed" -ge "$timeout" ]; then
      if [ "$REAP" = "1" ]; then
        echo "$session@$alias: timeout after ${timeout}s — reaping (AERO_RUN_LONG_REAP=1)" >&2
        cmd_kill "$alias" "$session" || true
      else
        echo "$session@$alias: still running after ${timeout}s (timeout)" >&2
        echo "  NOTE: the remote job is STILL RUNNING and now unattended." >&2
        echo "  Reap it with: $0 kill $alias $session" >&2
      fi
      return 2
    fi
    sleep "$interval"
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
  kill)   shift; [[ $# -eq 2 ]] || die "usage: run_long.sh kill <alias> <session>"; cmd_kill "$@" ;;
  -h | --help) usage 0 ;;
  *) cmd_submit "$@" ;;
esac
