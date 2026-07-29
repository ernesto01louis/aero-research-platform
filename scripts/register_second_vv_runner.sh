#!/usr/bin/env bash
# scripts/register_second_vv_runner.sh
#
# Register a SECOND self-hosted GitHub Actions runner (`aero-build-vv-2`) on
# aero-build, so the three self-hosted workflows stop serialising behind one another.
#
# WHY THIS IS A SCRIPT AND NOT SOMETHING THE AGENT RAN
# ----------------------------------------------------
# Claude Code's auto-mode classifier independently blocks persistent-infrastructure
# actions — registering a CI runner, authorising root SSH keys, installing services —
# even with a `Bash(ssh:*)` allow rule in settings.local.json and explicit operator
# authorisation in chat. That gate is deliberate and is not worth working around, so the
# work is packaged here for the operator to run. (Same pattern as the Stage-03
# runner registration.)
#
# WHY A SECOND RUNNER
# -------------------
# `vv-required` (the only REQUIRED check), `vv-smoke` and `provenance-completeness` all
# target `[self-hosted, vv]`, of which there is exactly one. Measured 2026-07-28:
# provenance-completeness sat queued 1h26m behind an in-progress vv-smoke, and a required
# check waited ~90 min behind non-required work. aero-build has 8 cores and idles around
# 0.5 load, so it can host two runners comfortably. Stage-20 FSI work makes this worse:
# a multi-hour moving-mesh or FSI job would block every PR gate behind it.
#
# WHAT IT DOES
# ------------
#   1. mints a short-lived registration token via `gh` (never printed, never stored)
#   2. clones the existing runner's binaries into ~/actions-runner-2
#   3. configures it as `aero-build-vv-2` with the same `vv` label
#   4. installs + starts it as a systemd service, like the first one
#
# USAGE (from the Proxmox host, where `gh` is authenticated):
#     scripts/register_second_vv_runner.sh
#
# To undo:
#     ssh aero-build 'cd ~/actions-runner-2 && sudo ./svc.sh stop && sudo ./svc.sh uninstall'
#     ssh aero-build 'cd ~/actions-runner-2 && ./config.sh remove --token <removal-token>'
#     gh api -X POST repos/:owner/:repo/actions/runners/remove-token --jq .token   # for the above

set -euo pipefail

REPO="${AERO_REPO:-ernesto01louis/aero-research-platform}"
HOST="${AERO_RUNNER_HOST:-aero-build}"
SRC="${AERO_RUNNER_SRC:-/home/aero-admin/actions-runner}"
DST="${AERO_RUNNER_DST:-/home/aero-admin/actions-runner-2}"
NAME="${AERO_RUNNER_NAME:-aero-build-vv-2}"
LABELS="${AERO_RUNNER_LABELS:-vv}"

command -v gh >/dev/null || { echo "gh CLI required (to mint the registration token)" >&2; exit 64; }

echo "==> preflight on ${HOST}"
ssh "$HOST" "test -d '$SRC'" || { echo "no existing runner at $SRC on $HOST" >&2; exit 65; }
if ssh "$HOST" "test -e '$DST'"; then
  echo "$DST already exists on $HOST — nothing to do (remove it first to re-register)" >&2
  exit 0
fi

echo "==> cloning runner binaries into $DST (identity + state stripped)"
ssh "$HOST" "
  set -e
  cp -a '$SRC' '$DST'
  rm -f  '$DST'/.runner '$DST'/.credentials '$DST'/.credentials_rsaparams '$DST'/.service '$DST'/.env
  rm -rf '$DST'/_work '$DST'/_diag
"

echo "==> configuring as '$NAME' (labels: $LABELS)"
# The token is piped over stdin and read into a shell variable on the remote side, so it
# never appears in a command line, a process list, an env dump, or this script's output
# (Hard Rule 7 — no secrets in logs).
gh api -X POST "repos/${REPO}/actions/runners/registration-token" --jq .token \
  | ssh "$HOST" "
      set -e
      read -r TOKEN
      cd '$DST'
      ./config.sh --unattended \
        --url 'https://github.com/${REPO}' \
        --token \"\$TOKEN\" \
        --name '$NAME' \
        --labels '$LABELS' \
        --work _work
    "

echo "==> installing + starting the service (as root: see note)"
# NOT `sudo ./svc.sh` as aero-admin. That account's NOPASSWD sudoers entry covers only
# /usr/bin/{apt,apt-get,systemctl,mount,umount,apptainer} — an arbitrary script is not on
# the list, so `sudo ./svc.sh install` prompts for a password and hangs a non-interactive
# run forever. `ssh root@<host>` is the project's documented break-glass path
# (docs/architecture/ssh-conventions.md); svc.sh still installs the unit to RUN as
# aero-admin, which is what the first runner does.
ssh "root@${HOST#*@}" "cd '$DST' && ./svc.sh install aero-admin && ./svc.sh start"

echo "==> verifying"
ssh "$HOST" "systemctl list-units 'actions.runner*' --no-pager --plain | head -5"
gh api "repos/${REPO}/actions/runners" \
  --jq '.runners[] | "  \(.name)\tstatus=\(.status)\tbusy=\(.busy)\tlabels=\([.labels[].name] | join(","))"'

echo
echo "Done. Both runners should now show status=online."
echo "The three self-hosted workflows will stop serialising; vv-required no longer"
echo "queues behind vv-smoke."
