#!/usr/bin/env bash
# scripts/build_jax_fluids_sif.sh — Stage 08 (ADR-008).
#
# Build, sign, and publish the JAX-Fluids solver SIF. Mirrors the
# Stage-07 PyFR build pattern (see scripts/build_pyfr_sif.sh):
#
#   1. Rootless `buildah` on the Proxmox HOST (has network) builds the
#      OCI image from containers/jax-fluids.Dockerfile and exports an
#      OCI archive to /mnt/aero-nfs/tmp/jax-fluids-oci.tar.
#   2. SSH to `aero-build`; apptainer 1.5+ bootstraps the SIF from that
#      archive, signs it (operator key), verifies, and publishes to
#      /mnt/aero/containers/jax-fluids.sif.
#   3. Print the SHA256 line to append to containers/SHA256SUMS.
#   4. Optionally push the OCI image to ghcr.io/ernesto01louis/aero-jax-fluids
#      so RunPod can pull it natively (RunPod's runtime is OCI, not
#      Apptainer). The GHCR digest goes into containers/SHA256SUMS as a
#      commented line so the four-fold provenance tuple resolves either way.
#
# Usage (on the Proxmox host with rootless buildah + network):
#   ./scripts/build_jax_fluids_sif.sh [<JAXFLUIDS_TAG>] [<repo-root>]
# Defaults: JAXFLUIDS_TAG=JAX-Fluids-v0.2.1 ; repo-root=$(pwd).
#
# For the JAX wheel install this takes ~5-10 min wall-clock. Run detached
# only if running under low-network conditions:
#   bash scripts/run_long.sh aero-build jaxf-build "./scripts/build_jax_fluids_sif.sh"

set -euo pipefail

JAXFLUIDS_TAG="${1:-JAX-Fluids-v0.2.1}"
REPO_ROOT="${2:-$(pwd)}"

IMAGE="localhost/aero/jax-fluids:${JAXFLUIDS_TAG}"
OCI_ARCHIVE_HOST="/mnt/aero-nfs/tmp/jax-fluids-oci.tar"
OCI_ARCHIVE_LXC="/mnt/aero/tmp/jax-fluids-oci.tar"
SIF_PUBLISH_PATH="/mnt/aero/containers/jax-fluids.sif"

echo ">> buildah bud — $IMAGE"
buildah bud \
    -f "${REPO_ROOT}/containers/jax-fluids.Dockerfile" \
    -t "${IMAGE}" \
    --build-arg "JAXFLUIDS_TAG=${JAXFLUIDS_TAG}" \
    "${REPO_ROOT}/containers/"

echo ">> buildah push -> ${OCI_ARCHIVE_HOST}"
mkdir -p "$(dirname "${OCI_ARCHIVE_HOST}")"
buildah push "${IMAGE}" "oci-archive:${OCI_ARCHIVE_HOST}"

echo ">> apptainer build on aero-build"
ssh root@aero-build "apptainer build --force ${SIF_PUBLISH_PATH} ${REPO_ROOT}/containers/jax-fluids.def"
ssh root@aero-build "apptainer sign ${SIF_PUBLISH_PATH}"
ssh root@aero-build "apptainer verify ${SIF_PUBLISH_PATH}"

echo ">> SHA256 to append to containers/SHA256SUMS:"
ssh root@aero-build "sha256sum ${SIF_PUBLISH_PATH}" | sed "s| ${SIF_PUBLISH_PATH}| jax-fluids.sif|"

cat <<'NEXT'

Next operator steps:
  1. Append the SHA256 line above to containers/SHA256SUMS.
  2. (Optional GHCR mirror, needed for RunPod cloud runs)
       buildah login ghcr.io                    # operator PAT
       buildah tag <localhost/aero/jax-fluids:JAX-Fluids-v0.2.1> \
                   ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
       buildah push  ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
     Capture the returned `sha256:<digest>` and append a comment line to
     containers/SHA256SUMS:
       # ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1 sha256:<digest>
NEXT
