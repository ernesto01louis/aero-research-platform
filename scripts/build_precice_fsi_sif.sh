#!/usr/bin/env bash
# scripts/build_precice_fsi_sif.sh
#
# Stage 19 (ADR-035) — build, sign and publish the coupled FSI solver SIF:
# OpenFOAM-ESI v2412 + preCICE 3.4.1 + the openfoam-adapter + a Nutils solid venv.
#
# SPLIT-HOST build, the Stage-07 pattern (scripts/build_pyfr_sif.sh):
#   step 1  buildah bud runs on the PROXMOX HOST, and pushes an OCI archive to the
#           shared NFS;
#   step 2  apptainer builds the SIF from that archive on aero-build, signs it, and
#           publishes to /mnt/aero/containers.
#
# Why not run buildah on aero-build: it is an unprivileged LXC, so a nested user
# namespace cannot map the subuid range — `newuidmap` is setuid but writing gid_map
# returns EPERM. buildah falls back to a single mapping, its slirp4netns networking
# never comes up, and every pull fails with "dial udp 192.168.2.1:53: socket:
# permission denied" even though curl from the same shell works. Confirmed at Stage 19
# with BUILDAH_ISOLATION=chroot and GODEBUG=netdns=cgo; neither helps. The host has
# buildah with its graphroot already on /mnt/pve/Storage.
#
# The adapter is compiled from source, so allow ~30-50 min. Submit it detached:
#   bash scripts/run_long.sh <alias> stage19-precice-sif "..."   # for the aero-build leg
# or simply run this script from the repo root on the Proxmox host.
#
# Usage (on the Proxmox host):  ./scripts/build_precice_fsi_sif.sh [repo-root]

set -euo pipefail

REPO_ROOT="${1:-$(pwd)}"
PRECICE_VERSION="3.4.1"
OCI_TAG="localhost/aero/precice-fsi:${PRECICE_VERSION}"
OCI_ARCHIVE_HOST="/mnt/aero-nfs/tmp/precice-fsi-oci.tar"
OCI_ARCHIVE_LXC="/mnt/aero/tmp/precice-fsi-oci.tar"
SIF="precice-fsi.sif"
DEF="${REPO_ROOT}/containers/precice-fsi.def"
DOCKERFILE="${REPO_ROOT}/containers/precice-fsi.Dockerfile"
CONTAINERS_LXC="/mnt/aero/containers"
SSH_TARGET="${AERO_BUILD_SSH:-root@aero-build}"
BUILD_DIR_LXC="/tmp/aero-precice-build"

log() { echo "[build-precice-fsi-sif] $*"; }

command -v buildah >/dev/null || { echo "buildah not installed on this host" >&2; exit 1; }
[ -f "$DOCKERFILE" ] || { echo "$DOCKERFILE not found" >&2; exit 1; }
[ -f "$DEF" ]        || { echo "$DEF not found" >&2; exit 1; }
mkdir -p "$(dirname "$OCI_ARCHIVE_HOST")"

# --- step 1: OCI build on the host (network available) ------------------------------
log "buildah bud — OpenFOAM v2412 + preCICE ${PRECICE_VERSION} + adapter + Nutils"
buildah bud \
    --layers=true \
    -f "$DOCKERFILE" \
    -t "$OCI_TAG" \
    "${REPO_ROOT}/containers"

# Record what actually went in — for ADR-035 and the post-stage handoff.
# `buildah run` needs a working CONTAINER, not an image, so make a throwaway one.
INSPECT_CTR="$(buildah from --quiet "$OCI_TAG")"
log "openfoam-adapter commit baked into the image:"
buildah run "$INSPECT_CTR" cat /opt/aero/openfoam-adapter.commit
log "solid participant stack:"
buildah run "$INSPECT_CTR" cat /opt/aero/solid-venv-freeze.txt
buildah rm "$INSPECT_CTR" >/dev/null

log "pushing OCI image to ${OCI_ARCHIVE_HOST}"
rm -f "$OCI_ARCHIVE_HOST"
buildah push "$OCI_TAG" "oci-archive:${OCI_ARCHIVE_HOST}"

# --- step 2: Apptainer SIF on aero-build (no network needed in %post) ---------------
log "apptainer build on ${SSH_TARGET} from ${OCI_ARCHIVE_LXC}"
ssh -o BatchMode=yes "$SSH_TARGET" "mkdir -p ${BUILD_DIR_LXC}"
scp -q "$DEF" "${SSH_TARGET}:${BUILD_DIR_LXC}/precice-fsi.def"
ssh -o BatchMode=yes "$SSH_TARGET" "set -euo pipefail
    [ -f /root/.config/aero/signing.env ] || { echo 'signing.env absent' >&2; exit 1; }
    cd ${BUILD_DIR_LXC}
    # Keep apptainer's cache and scratch on local disk: squashfs over NFS is slow and
    # unreliable, and a large pull can wedge a small root volume (Stage 09 precedent).
    export APPTAINER_CACHEDIR=${BUILD_DIR_LXC}/cache
    export APPTAINER_TMPDIR=${BUILD_DIR_LXC}/tmp
    mkdir -p \"\$APPTAINER_CACHEDIR\" \"\$APPTAINER_TMPDIR\"
    apptainer build --force ${SIF} precice-fsi.def
    # shellcheck disable=SC1091
    source /root/.config/aero/signing.env
    echo \"\$AERO_SIGNING_PASSPHRASE\" | apptainer sign ${SIF}
    apptainer verify ${SIF} || echo 'WARN: verify failed (unsigned?) — the SHA256 is still the integrity check'
    mkdir -p ${CONTAINERS_LXC}
    cp ${SIF} ${CONTAINERS_LXC}/
    sha256sum ${CONTAINERS_LXC}/${SIF}
"

echo
log "done — append the SHA256 line above to containers/SHA256SUMS"
