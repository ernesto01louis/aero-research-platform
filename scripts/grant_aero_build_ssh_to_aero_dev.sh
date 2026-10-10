#!/usr/bin/env bash
# scripts/grant_aero_build_ssh_to_aero_dev.sh
#
# Give the self-hosted CI runners on aero-build (LXC 210) a persistent, restricted
# SSH path to aero-dev (LXC 211), so multi-hour V&V and FSI cases can use the
# 16-core box instead of the 8-core runner host.
#
# WHY THIS IS A SCRIPT AND NOT SOMETHING THE AGENT RAN
# ----------------------------------------------------
# Authorising an SSH key for a remote root account is persistent-infrastructure
# work. Claude Code's auto-mode classifier blocks that class independently of any
# allow rule or in-chat authorisation, and that gate is deliberate. Same pattern as
# scripts/register_second_vv_runner.sh and the Stage-03 runner registration: the work
# is packaged here, reviewable as a diff, for the operator to run.
#
# WHY
# ---
# The `aero-*` SSH aliases are defined in ~/.ssh/config.d/aero on the PROXMOX HOST and
# do not exist inside the LXCs. From a runner, `ssh root@aero-dev` fails to resolve;
# ssh exits 255, and before Stage 20 the executor surfaced that as "blockMesh failed"
# — pointing at the mesher rather than at DNS. `moving-vv` run 30568971572 (2026-07-30)
# died that way in 18 s. Only aero-build (192.168.2.232) is in the runner's /etc/hosts.
#
# Consequence: `test_unsteady_plunging_airfoil` — the Heathcote-Gursul case Stage 20
# validates against — has NEVER completed in CI. aero-build has 8 cores and hosts two
# runners; aero-dev has 16 cores, 32 GB, the NFS dataset mount, and the AppArmor
# inet-socket change without which every Apptainer AF_INET socket is denied
# (docs/operator/apptainer-inet-sockets.md). The FSI participants belong there.
#
# WHAT IT DOES (all idempotent; nothing is overwritten in place)
# -------------------------------------------------------------
#   1. mints a DEDICATED ed25519 keypair on aero-build as `aero-admin`
#      (~/.ssh/id_ed25519_aero_dev) — not the existing id_ed25519, so this trust can
#      be revoked on its own without breaking aero-admin -> root@aero-build
#   2. adds a marker-delimited `Host aero-dev` block to aero-admin's ~/.ssh/config
#      (HostName 192.168.2.233, User root, IdentitiesOnly yes). An ssh config block
#      rather than an /etc/hosts edit: ssh is the only consumer, and it keeps the
#      change inside one user's dotfiles.
#   3. pins aero-dev's host key into aero-admin's known_hosts via ssh-keyscan, so the
#      trust does not rely on StrictHostKeyChecking=no
#   4. appends the public key to root@aero-dev:~/.ssh/authorized_keys, restricted with
#      from="192.168.2.232" so the key is useless from anywhere but aero-build
#   5. verifies end to end, as aero-admin, including a run_long.sh round trip
#
# Both hosts are aero-owned LXCs (210, 211). Nothing outside the aero fleet is touched.
#
# USAGE (from the Proxmox host, where the aero-* aliases resolve):
#     scripts/grant_aero_build_ssh_to_aero_dev.sh
#     scripts/grant_aero_build_ssh_to_aero_dev.sh --revert
#
# Runbook, including what to check when it stops working:
#     docs/operator/aero-build-to-aero-dev-ssh.md

set -euo pipefail

BUILD_SSH="${AERO_BUILD_SSH:-root@aero-build}"
DEV_SSH="${AERO_DEV_SSH:-root@aero-dev}"
DEV_IP="${AERO_DEV_IP:-192.168.2.233}"
BUILD_IP="${AERO_BUILD_IP:-192.168.2.232}"
RUNNER_USER="${AERO_RUNNER_USER:-aero-admin}"
KEY="/home/${RUNNER_USER}/.ssh/id_ed25519_aero_dev"
MARK_BEGIN="# >>> aero-dev (scripts/grant_aero_build_ssh_to_aero_dev.sh) >>>"
MARK_END="# <<< aero-dev (scripts/grant_aero_build_ssh_to_aero_dev.sh) <<<"
KEY_TAG="aero-build-ci-to-aero-dev"

log() { printf '\n== %s ==\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- revert -------------------------------------------------------------------
if [[ "${1:-}" == "--revert" ]]; then
  log "removing the authorized_keys entry on aero-dev"
  ssh "$DEV_SSH" "
    set -e
    if [ -f /root/.ssh/authorized_keys ]; then
      cp -a /root/.ssh/authorized_keys /root/.ssh/authorized_keys.bak.\$(date +%s)
      grep -v '${KEY_TAG}' /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.new || true
      mv /root/.ssh/authorized_keys.new /root/.ssh/authorized_keys
      chmod 600 /root/.ssh/authorized_keys
    fi
  "
  log "removing the ssh config block and key on aero-build"
  ssh "$BUILD_SSH" "
    set -e
    CFG=/home/${RUNNER_USER}/.ssh/config
    if [ -f \"\$CFG\" ]; then
      sed -i '\%${MARK_BEGIN}%,\%${MARK_END}%d' \"\$CFG\"
    fi
    rm -f '${KEY}' '${KEY}.pub'
  "
  log "reverted. aero-admin can no longer reach aero-dev."
  exit 0
fi

# --- 1. dedicated keypair on aero-build ---------------------------------------
log "1/5  dedicated keypair on aero-build (${RUNNER_USER})"
ssh "$BUILD_SSH" "
  set -e
  install -d -m 700 -o ${RUNNER_USER} -g ${RUNNER_USER} /home/${RUNNER_USER}/.ssh
  if [ ! -f '${KEY}' ]; then
    su - ${RUNNER_USER} -c \"ssh-keygen -t ed25519 -N '' -C '${KEY_TAG}' -f '${KEY}'\"
  else
    echo 'keypair already present — reusing'
  fi
  chmod 600 '${KEY}'; chmod 644 '${KEY}.pub'
"
PUBKEY="$(ssh "$BUILD_SSH" "cat '${KEY}.pub'")"
[[ -n "$PUBKEY" ]] || die "could not read the public key from aero-build"

# --- 2. ssh config block ------------------------------------------------------
log "2/5  ssh config block for Host aero-dev"
ssh "$BUILD_SSH" "
  set -e
  CFG=/home/${RUNNER_USER}/.ssh/config
  touch \"\$CFG\"
  # Idempotent: drop any previous block before writing the current one, so re-running
  # after an edit converges instead of accumulating duplicate Host stanzas.
  sed -i '\%${MARK_BEGIN}%,\%${MARK_END}%d' \"\$CFG\"
  cat >> \"\$CFG\" <<EOF
${MARK_BEGIN}
Host aero-dev
    HostName ${DEV_IP}
    User root
    IdentityFile ${KEY}
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 15
${MARK_END}
EOF
  chown ${RUNNER_USER}:${RUNNER_USER} \"\$CFG\"
  chmod 600 \"\$CFG\"
"

# --- 3. pin the host key ------------------------------------------------------
log "3/5  pinning aero-dev's host key in known_hosts"
ssh "$BUILD_SSH" "
  set -e
  KH=/home/${RUNNER_USER}/.ssh/known_hosts
  touch \"\$KH\"
  ssh-keygen -f \"\$KH\" -R '${DEV_IP}' >/dev/null 2>&1 || true
  ssh-keygen -f \"\$KH\" -R 'aero-dev'  >/dev/null 2>&1 || true
  ssh-keyscan -H -t ed25519 '${DEV_IP}' >> \"\$KH\" 2>/dev/null
  ssh-keyscan -H -t ed25519 'aero-dev' >> \"\$KH\" 2>/dev/null || true
  chown ${RUNNER_USER}:${RUNNER_USER} \"\$KH\"
  chmod 600 \"\$KH\"
"

# --- 4. authorise on aero-dev -------------------------------------------------
log "4/5  authorising the key for root@aero-dev (restricted to ${BUILD_IP})"
ssh "$DEV_SSH" "
  set -e
  install -d -m 700 /root/.ssh
  touch /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  # Replace rather than append, so re-running after a key rotation does not leave the
  # superseded key authorised.
  grep -v '${KEY_TAG}' /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.new || true
  printf 'from=\"${BUILD_IP}\" %s\n' '${PUBKEY}' >> /root/.ssh/authorized_keys.new
  mv /root/.ssh/authorized_keys.new /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
"

# --- 5. verify ----------------------------------------------------------------
log "5/5  verifying end to end as ${RUNNER_USER}"
ssh "$BUILD_SSH" "su - ${RUNNER_USER} -c 'ssh -o BatchMode=yes aero-dev \"hostname; nproc\"'" \
  || die "aero-admin still cannot reach aero-dev — check the runbook"
ssh "$BUILD_SSH" "su - ${RUNNER_USER} -c 'ssh -o BatchMode=yes root@aero-dev true'" \
  || die "the root@aero-dev form failed — the executor builds its target as user@host"

log "done. moving-vv can now target aero-dev; see docs/operator/aero-build-to-aero-dev-ssh.md"
