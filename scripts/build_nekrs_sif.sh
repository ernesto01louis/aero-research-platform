#!/usr/bin/env bash
# scripts/build_nekrs_sif.sh
#
# Stage 07 — build, sign, and publish the NekRS solver SIF.
#
# Two-step build (ADR-007). Same shape as build_pyfr_sif.sh except the
# buildah step is ~30-45 min wall-clock (cmake + parallel make of NekRS +
# OCCA + libParanumal across sm_80/sm_89/sm_90 CUDA archs), so this script
# must be submitted as a detached background job on the Proxmox host —
# either:
#
#   nohup bash scripts/build_nekrs_sif.sh > /var/log/aero/nekrs-build.log 2>&1 &
#
# or under tmux. The script tail's progress to stdout so the run_long.sh
# wrapper sentinel pattern (.done / .failed) flows through normally.
#
# Usage:
#   ./scripts/build_nekrs_sif.sh [<NEKRS_REF>] [<repo-root>]
# Defaults: NEKRS_REF=v23.0; repo-root=$(pwd).

set -euo pipefail

NEKRS_REF="${1:-v23.0}"
REPO_ROOT="${2:-$(pwd)}"
CUDA_VERSION="${CUDA_VERSION:-12.4.1}"
OCI_TAG="localhost/aero/nekrs:${NEKRS_REF}"
OCI_ARCHIVE_HOST="/mnt/aero-nfs/tmp/nekrs-oci.tar"
OCI_ARCHIVE_LXC="/mnt/aero/tmp/nekrs-oci.tar"
SIF="nekrs.sif"
DEF="${REPO_ROOT}/containers/nekrs.def"
DOCKERFILE="${REPO_ROOT}/containers/nekrs.Dockerfile"
CONTAINERS_LXC="/mnt/aero/containers"
SSH_TARGET="${AERO_BUILD_SSH:-root@aero-build}"

log() { echo "[build-nekrs-sif] $*"; }

command -v buildah >/dev/null || { echo "buildah not installed on this host" >&2; exit 1; }
[ -f "$DOCKERFILE" ] || { echo "$DOCKERFILE not found" >&2; exit 1; }
[ -f "$DEF" ]        || { echo "$DEF not found" >&2; exit 1; }
mkdir -p "$(dirname "$OCI_ARCHIVE_HOST")"

# --- step 1: OCI source-build of NekRS (~30-45 min) ------------------------
log "buildah bud — NekRS ${NEKRS_REF} on CUDA ${CUDA_VERSION}  (long compile)"
buildah bud \
    --layers=true \
    --pull-always \
    --build-arg "NEKRS_REF=${NEKRS_REF}" \
    --build-arg "CUDA_VERSION=${CUDA_VERSION}" \
    -f "$DOCKERFILE" \
    -t "$OCI_TAG" \
    "${REPO_ROOT}/containers"

log "captured NekRS commit SHA:"
buildah run "$OCI_TAG" cat /opt/nekrs/.nekrs-version

log "pushing OCI image to ${OCI_ARCHIVE_HOST}"
rm -f "$OCI_ARCHIVE_HOST"
buildah push "$OCI_TAG" "oci-archive:${OCI_ARCHIVE_HOST}"

# --- step 2: Apptainer SIF on aero-build ----------------------------------
log "apptainer build on ${SSH_TARGET} from ${OCI_ARCHIVE_LXC}"
ssh -o BatchMode=yes "$SSH_TARGET" "mkdir -p /tmp/aero-nekrs-build"
scp "$DEF" "$SSH_TARGET":/tmp/aero-nekrs-build/nekrs.def
ssh -o BatchMode=yes "$SSH_TARGET" "set -euo pipefail
    [ -f /root/.config/aero/signing.env ] || { echo 'signing.env absent' >&2; exit 1; }
    # shellcheck disable=SC1091
    source /root/.config/aero/signing.env
    cd /tmp/aero-nekrs-build
    apptainer build --force ${SIF} nekrs.def
    echo \"\$AERO_SIGNING_PASSPHRASE\" | apptainer sign ${SIF}
    apptainer verify ${SIF}
    mkdir -p ${CONTAINERS_LXC}
    cp ${SIF} ${CONTAINERS_LXC}/
    sha256sum ${CONTAINERS_LXC}/${SIF}
"

echo
log "NekRS SIF published; append this line to containers/SHA256SUMS:"
ssh -o BatchMode=yes "$SSH_TARGET" "cd ${CONTAINERS_LXC} && sha256sum ${SIF}"
