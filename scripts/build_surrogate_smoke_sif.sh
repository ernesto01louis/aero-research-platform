#!/usr/bin/env bash
# scripts/build_surrogate_smoke_sif.sh — Stage 08 (ADR-008).
#
# Build, sign, and publish the surrogate-smoke SIF (Torch + PyG, no JAX).
# Mirrors the Stage-08 JAX-Fluids build pattern.
#
# Usage (on the Proxmox host with rootless buildah + network):
#   ./scripts/build_surrogate_smoke_sif.sh [<TORCH_VERSION>] [<PYG_VERSION>] [<repo-root>]
# Defaults: TORCH_VERSION=2.5.1 ; PYG_VERSION=2.6.1 ; repo-root=$(pwd).

set -euo pipefail

TORCH_VERSION="${1:-2.5.1}"
PYG_VERSION="${2:-2.6.1}"
REPO_ROOT="${3:-$(pwd)}"

IMAGE="localhost/aero/surrogate-smoke:torch-${TORCH_VERSION}-pyg-${PYG_VERSION}"
OCI_ARCHIVE_HOST="/mnt/aero-nfs/tmp/surrogate-smoke-oci.tar"
SIF_PUBLISH_PATH="/mnt/aero/containers/surrogate-smoke.sif"

echo ">> buildah bud — $IMAGE"
buildah bud \
    -f "${REPO_ROOT}/containers/surrogate-smoke.Dockerfile" \
    -t "${IMAGE}" \
    --build-arg "TORCH_VERSION=${TORCH_VERSION}" \
    --build-arg "PYG_VERSION=${PYG_VERSION}" \
    "${REPO_ROOT}/containers/"

echo ">> buildah push -> ${OCI_ARCHIVE_HOST}"
mkdir -p "$(dirname "${OCI_ARCHIVE_HOST}")"
buildah push "${IMAGE}" "oci-archive:${OCI_ARCHIVE_HOST}"

echo ">> apptainer build on aero-build"
ssh root@aero-build "apptainer build --force ${SIF_PUBLISH_PATH} ${REPO_ROOT}/containers/surrogate-smoke.def"
ssh root@aero-build "apptainer sign ${SIF_PUBLISH_PATH}"
ssh root@aero-build "apptainer verify ${SIF_PUBLISH_PATH}"

echo ">> SHA256 to append to containers/SHA256SUMS:"
ssh root@aero-build "sha256sum ${SIF_PUBLISH_PATH}" | sed "s| ${SIF_PUBLISH_PATH}| surrogate-smoke.sif|"

cat <<'NEXT'

Next operator steps:
  1. Append the SHA256 line above to containers/SHA256SUMS.
  2. GHCR mirror for RunPod cloud runs:
       buildah tag <local-image> ghcr.io/ernesto01louis/aero-surrogate-smoke:<tag>
       buildah push  ghcr.io/ernesto01louis/aero-surrogate-smoke:<tag>
     Append the digest as a comment line to containers/SHA256SUMS.
NEXT
