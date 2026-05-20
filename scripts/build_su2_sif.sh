#!/usr/bin/env bash
# scripts/build_su2_sif.sh
#
# Stage 06 — build, sign, and publish the SU2 v8 solver SIF.
#
# Two-step build (ADR-006): rootless `buildah` source-builds SU2 v8 into an
# OCI image (network is available — `slirp4netns`, unlike the Apptainer build
# sandbox which is socket-blocked in the unprivileged aero-build LXC, Stage
# 02 §6); the SIF then bootstraps from that OCI archive filesystem-only.
#
# Runs ON aero-build as root (the LXC root; SIFs build as the LXC root —
# Stage 02 precedent). The buildah step works as root in the LXC; for a
# rootless variant on a developer host, set BUILDAH_USER and adjust.
#
# Builds, signs, verifies, and publishes:
#   su2-v8.sif — SU2 v8.x source build with pysu2 / autodiff / Mutation++
# to /mnt/aero/containers/, then prints the SHA256 line to record in
# containers/SHA256SUMS.
#
# Prerequisites: Apptainer, buildah; the TrueNAS aero/ export bind-mounted
# at /mnt/aero; the Stage 02 signing keypair present (scripts/build_base_sifs.sh
# generated it); containers/su2-v8.{Dockerfile,def}.
#
# Usage (on aero-build, as root):
#   ./scripts/build_su2_sif.sh [<SU2_VERSION>] [<repo-root>]
# Defaults: SU2_VERSION=v8.1.0; repo-root=$(pwd).

set -euo pipefail

SU2_VERSION="${1:-v8.1.0}"
REPO_ROOT="${2:-$(pwd)}"
OCI_TAG="localhost/aero/su2-v8:${SU2_VERSION}"
OCI_ARCHIVE="/tmp/su2-v8-oci.tar"
SIF="su2-v8.sif"
DEF="${REPO_ROOT}/containers/su2-v8.def"
DOCKERFILE="${REPO_ROOT}/containers/su2-v8.Dockerfile"
CONTAINERS="/mnt/aero/containers"
PASSFILE="/root/.config/aero/signing.env"
BUILD_DIR="/tmp/aero-su2-build"

log() { echo "[build-su2-sif] $*"; }

command -v apptainer >/dev/null || { echo "apptainer not installed" >&2; exit 1; }
command -v buildah   >/dev/null || { echo "buildah not installed" >&2; exit 1; }
[ -f "$DOCKERFILE" ] || { echo "$DOCKERFILE not found" >&2; exit 1; }
[ -f "$DEF" ]        || { echo "$DEF not found" >&2; exit 1; }
[ -f "$PASSFILE" ]   || { echo "$PASSFILE absent — run build_base_sifs.sh first" >&2; exit 1; }

# shellcheck disable=SC1090
source "$PASSFILE"

mkdir -p "$BUILD_DIR"

# --- step 1: OCI source build of SU2 (network available) -------------------
log "buildah bud — SU2 ${SU2_VERSION} (autodiff, mpp, pysu2; OpenBLAS, no MKL)"
buildah bud \
    --pull-always \
    --build-arg "SU2_VERSION=${SU2_VERSION}" \
    -f "$DOCKERFILE" \
    -t "$OCI_TAG" \
    "${REPO_ROOT}/containers"

# Record the captured SU2 commit SHA — for ADR-006 / the post-stage handoff.
log "captured SU2 commit SHA:"
buildah run "$OCI_TAG" cat /opt/su2/.su2-commit

log "pushing OCI image to ${OCI_ARCHIVE}"
rm -f "$OCI_ARCHIVE"
buildah push "$OCI_TAG" "oci-archive:${OCI_ARCHIVE}"

# --- step 2: Apptainer SIF from the OCI archive (no network) ---------------
log "building ${SIF} from oci-archive (filesystem-only %post)"
apptainer build --force "${BUILD_DIR}/${SIF}" "$DEF"

log "signing ${SIF}"
echo "$AERO_SIGNING_PASSPHRASE" | apptainer sign "${BUILD_DIR}/${SIF}"
apptainer verify "${BUILD_DIR}/${SIF}"

mkdir -p "$CONTAINERS"
cp "${BUILD_DIR}/${SIF}" "$CONTAINERS/"
log "published to ${CONTAINERS}/${SIF}"

echo
log "SHA256 (append this line to containers/SHA256SUMS):"
(cd "$CONTAINERS" && sha256sum "$SIF")
