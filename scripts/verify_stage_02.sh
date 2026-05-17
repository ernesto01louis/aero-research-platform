#!/usr/bin/env bash
# scripts/verify_stage_02.sh
#
# Stage 02 gate. Exits 0 iff every check passes; 1 otherwise. Every check
# runs and reports PASS/FAIL (the script does not use `set -e`, so one
# failure does not mask the rest). Run from anywhere; paths resolve off the
# script location.
#
# Checks: SSH reachability of all 7 aero LXCs; Apptainer >= pinned version on
# build+dev; the hello-world SIF runs; containers/SHA256SUMS is complete and
# matches the live SIFs; the TrueNAS NFS mount; tmux everywhere; read-only
# reachability of shared Postgres 202 and Grafana 205; the run_long.sh
# submit/poll round-trip.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALIASES=(aero-build aero-dev aero-mlflow aero-vv aero-prefect aero-agent aero-lit)
NFS_NODES=(aero-build aero-dev aero-vv aero-mlflow)
APPTAINER_MIN="1.5.0"
POSTGRES_HOST="192.168.2.184"; POSTGRES_PORT="5432"
GRAFANA_HOST="192.168.2.188";  GRAFANA_PORT="3000"
SUMS="$REPO_ROOT/containers/SHA256SUMS"

pass=0; fail=0
ok()  { echo "  PASS  $*"; pass=$((pass + 1)); }
bad() { echo "  FAIL  $*"; fail=$((fail + 1)); }
ssh_q() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$@"; }

echo "== Stage 02 verification =="

echo "[1] SSH reachability of the aero fleet"
for a in "${ALIASES[@]}"; do
  if ssh_q "$a" true 2>/dev/null; then ok "$a reachable"; else bad "$a unreachable"; fi
done

echo "[2] Apptainer >= $APPTAINER_MIN on build + dev"
for a in aero-build aero-dev; do
  v=$(ssh_q "$a" "apptainer --version 2>/dev/null" | awk '{print $NF}')
  if [[ -n "$v" ]] && printf '%s\n%s\n' "$APPTAINER_MIN" "$v" | sort -V -C 2>/dev/null; then
    ok "$a apptainer $v"
  else
    bad "$a apptainer '${v:-absent}' (need >= $APPTAINER_MIN)"
  fi
done

echo "[3] hello-world SIF runs on aero-build"
out=$(ssh_q aero-build "apptainer run /opt/aero/containers/hello-world.sif 2>/dev/null")
if [[ "$out" == *"hello aero"* ]]; then ok "hello-world.sif prints 'hello aero'"
else bad "hello-world.sif output: '${out:-<none>}'"; fi

echo "[4] containers/SHA256SUMS complete and matching"
for f in _base.sif hello-world.sif; do
  want=$(grep -E "[[:space:]]${f//./\\.}\$" "$SUMS" 2>/dev/null | awk '{print $1}')
  if [[ -n "$want" ]]; then
    ok "SHA256SUMS records $f"
    got=$(ssh_q aero-build "sha256sum /opt/aero/containers/$f 2>/dev/null" | awk '{print $1}')
    if [[ -n "$got" && "$got" == "$want" ]]; then ok "$f live SHA256 matches"
    else bad "$f SHA256 mismatch (recorded=$want live=${got:-<none>})"; fi
  else
    bad "SHA256SUMS missing $f"
  fi
done

echo "[5] TrueNAS NFS mounted at /mnt/aero"
for a in "${NFS_NODES[@]}"; do
  if ssh_q "$a" "mountpoint -q /mnt/aero && test -d /mnt/aero/containers"; then
    ok "$a /mnt/aero mounted"
  else bad "$a /mnt/aero not mounted"; fi
done

echo "[6] tmux present on every aero LXC"
for a in "${ALIASES[@]}"; do
  if ssh_q "$a" "command -v tmux >/dev/null"; then ok "$a tmux"; else bad "$a tmux missing"; fi
done

echo "[7] shared Postgres 202 reachable from aero-mlflow"
if ssh_q aero-mlflow "timeout 5 bash -c '</dev/tcp/$POSTGRES_HOST/$POSTGRES_PORT' 2>/dev/null"; then
  ok "aero-mlflow -> $POSTGRES_HOST:$POSTGRES_PORT"
else bad "aero-mlflow cannot reach $POSTGRES_HOST:$POSTGRES_PORT"; fi

echo "[8] shared Grafana 205 reachable from aero-vv"
if ssh_q aero-vv "timeout 5 bash -c '</dev/tcp/$GRAFANA_HOST/$GRAFANA_PORT' 2>/dev/null"; then
  ok "aero-vv -> $GRAFANA_HOST:$GRAFANA_PORT"
else bad "aero-vv cannot reach $GRAFANA_HOST:$GRAFANA_PORT"; fi

echo "[9] run_long.sh submit / poll round-trip"
sess="verify$(date +%s)"
t0=$(date +%s)
"$REPO_ROOT/scripts/run_long.sh" aero-build "$sess" "sleep 30" >/dev/null 2>&1
submit_secs=$(( $(date +%s) - t0 ))
if [[ "$submit_secs" -le 8 ]]; then ok "run_long submit returned immediately (${submit_secs}s)"
else bad "run_long submit took ${submit_secs}s (expected immediate)"; fi
sleep 5
st=$("$REPO_ROOT/scripts/run_long.sh" status aero-build "$sess" 2>/dev/null || true)
if [[ "$st" == *running* ]]; then ok "job still running at 5s"
else bad "unexpected job state at 5s: ${st:-<none>}"; fi
if "$REPO_ROOT/scripts/run_long.sh" wait aero-build "$sess" 60 >/dev/null 2>&1; then
  ok "run_long .done sentinel appeared"
else bad "run_long .done did not appear within 60s"; fi
ssh_q aero-build "rm -rf ~/.aero-jobs/$sess" >/dev/null 2>&1 || true

echo
echo "== $pass passed, $fail failed =="
if [[ "$fail" -eq 0 ]]; then echo "Stage 02 verification: PASS"; exit 0
else echo "Stage 02 verification: FAIL"; exit 1; fi
