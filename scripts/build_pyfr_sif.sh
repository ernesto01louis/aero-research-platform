#!/usr/bin/env bash
# scripts/build_pyfr_sif.sh
#
# Stage 07 — build, sign, and publish the PyFR solver SIF.
#
# Two-step build (ADR-007, inheriting ADR-006): rootless `buildah` runs the
# PyFR + CUDA install with network access on the Proxmox HOST (where the
# nested-namespace AppArmor/seccomp profile permits outbound sockets, unlike
# the unprivileged aero-build LXC — Stage 06 operator-followups §1a). The
# Apptainer step then runs on aero-build, where signing key + apptainer 1.5
# live (Stage 06 §1b). The OCI archive is handed over via the shared NFS
# dataset (`/mnt/aero-nfs/tmp/` on the host == `/mnt/aero/tmp/` on aero-build).
#
# Usage (host with rootless buildah + network):
#   ./scripts/build_pyfr_sif.sh [<PYFR_VERSION>] [<repo-root>]
# Defaults: PYFR_VERSION=1.15.0; repo-root=$(pwd).
#
# After the buildah step succeeds, this script SSHes to aero-build, runs the
# apptainer build + sign + verify, publishes to /mnt/aero/containers/, and
# prints the SHA256 line to record in containers/SHA256SUMS.
#
# For long compiles, prefer:
#   bash scripts/run_long.sh aero-build pyfr-build "./scripts/build_pyfr_sif.sh"
# — but the buildah step here is short (~10-15 min); see build_nekrs_sif.sh
# for the script that *must* run detached.

set -euo pipefail

PYFR_VERSION="${1:-1.15.0}"
REPO_ROOT="${2:-$(pwd)}"
CUDA_VERSION="${CUDA_VERSION:-12.4.1}"
OCI_TAG="localhost/aero/pyfr:${PYFR_VERSION}"
OCI_ARCHIVE_HOST="/mnt/aero-nfs/tmp/pyfr-oci.tar"
OCI_ARCHIVE_LXC="/mnt/aero/tmp/pyfr-oci.tar"
SIF="pyfr.sif"
DEF="${REPO_ROOT}/containers/pyfr.def"
DOCKERFILE="${REPO_ROOT}/containers/pyfr.Dockerfile"
CONTAINERS_LXC="/mnt/aero/containers"
SSH_TARGET="${AERO_BUILD_SSH:-root@aero-build}"

log() { echo "[build-pyfr-sif] $*"; }

command -v buildah >/dev/null || { echo "buildah not installed on this host" >&2; exit 1; }
[ -f "$DOCKERFILE" ] || { echo "$DOCKERFILE not found" >&2; exit 1; }
[ -f "$DEF" ]        || { echo "$DEF not found" >&2; exit 1; }
mkdir -p "$(dirname "$OCI_ARCHIVE_HOST")"

# --- step 1: OCI build of PyFR (network available on the host) -------------
log "buildah bud — PyFR ${PYFR_VERSION} on CUDA ${CUDA_VERSION}"
buildah bud \
    --layers=true \
    --pull-always \
    --build-arg "PYFR_VERSION=${PYFR_VERSION}" \
    --build-arg "CUDA_VERSION=${CUDA_VERSION}" \
    -f "$DOCKERFILE" \
    -t "$OCI_TAG" \
    "${REPO_ROOT}/containers"

log "pushing OCI image to ${OCI_ARCHIVE_HOST}"
rm -f "$OCI_ARCHIVE_HOST"
buildah push "$OCI_TAG" "oci-archive:${OCI_ARCHIVE_HOST}"

# --- step 2: Apptainer SIF on aero-build (no network needed) ---------------
log "apptainer build on ${SSH_TARGET} from ${OCI_ARCHIVE_LXC}"
ssh -o BatchMode=yes "$SSH_TARGET" "set -euo pipefail
    [ -f /root/.config/aero/signing.env ] || { echo 'signing.env absent' >&2; exit 1; }
    # shellcheck disable=SC1091
    source /root/.config/aero/signing.env
    mkdir -p /tmp/aero-pyfr-build
    cd /tmp/aero-pyfr-build
    apptainer build --force ${SIF} ${DEF}
    echo \"\$AERO_SIGNING_PASSPHRASE\" | apptainer sign ${SIF}
    apptainer verify ${SIF}
    mkdir -p ${CONTAINERS_LXC}
    cp ${SIF} ${CONTAINERS_LXC}/
    sha256sum ${CONTAINERS_LXC}/${SIF}
" || {
    # The remote def file lives in the repo, not on aero-build. Stage 06 SU2
    # built the def in /tmp via `git clone`; for Stage 07 we copy the def
    # directly via scp since the def path on aero-build needs to exist.
    log "first attempt failed (def path may not exist on aero-build); retrying with scp'd def"
    ssh -o BatchMode=yes "$SSH_TARGET" "mkdir -p /tmp/aero-pyfr-build"
    scp "$DEF" "$SSH_TARGET":/tmp/aero-pyfr-build/pyfr.def
    ssh -o BatchMode=yes "$SSH_TARGET" "set -euo pipefail
        # shellcheck disable=SC1091
        source /root/.config/aero/signing.env
        cd /tmp/aero-pyfr-build
        apptainer build --force ${SIF} pyfr.def
        echo \"\$AERO_SIGNING_PASSPHRASE\" | apptainer sign ${SIF}
        apptainer verify ${SIF}
        mkdir -p ${CONTAINERS_LXC}
        cp ${SIF} ${CONTAINERS_LXC}/
        sha256sum ${CONTAINERS_LXC}/${SIF}
    "
}

echo
log "PyFR SIF published; append this line to containers/SHA256SUMS:"
ssh -o BatchMode=yes "$SSH_TARGET" "cd ${CONTAINERS_LXC} && sha256sum ${SIF}"
