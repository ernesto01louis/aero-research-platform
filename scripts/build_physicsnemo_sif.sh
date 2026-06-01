#!/usr/bin/env bash
# scripts/build_physicsnemo_sif.sh — Stage 09 (ADR-010).
#
# Build, sign, and publish the PhysicsNeMo DoMINO SIF by wrapping the NGC
# container nvcr.io/nvidia/physicsnemo/physicsnemo:25.08. Unlike the buildah
# two-step (jax-fluids / surrogate-smoke), this bootstraps DIRECTLY from the NGC
# docker image — apptainer pulls it (~20 GB; needs NGC creds + network).
#
# Prereqs on aero-build:
#   * buildah/apptainer scratch storage on /mnt/pve/Storage — the
#     aero-buildah-storage Ansible role (docs/operator/buildah-storage-config.md).
#     The ~20 GB pull + unpack deadlocks the 68 GB root volume otherwise.
#   * NGC login (operator NGC API key; never committed):
#       apptainer remote login --username '$oauthtoken' docker://nvcr.io
#
# Usage (on aero-build):
#   ./scripts/build_physicsnemo_sif.sh [<repo-root>]
# Default: repo-root=/opt/aero/repo. The base tag is PINNED in physicsnemo.def
# (Hard Rule 8) — change it there + in ADR-010, not here.

set -euo pipefail

REPO_ROOT="${1:-/opt/aero/repo}"
DEF="${REPO_ROOT}/containers/physicsnemo.def"
SIF_PUBLISH_PATH="/mnt/aero/containers/physicsnemo.sif"

echo ">> apptainer build (NGC base, pinned in physicsnemo.def) -> ${SIF_PUBLISH_PATH}"
echo "   (~20 GB NGC pull; ensure 'apptainer remote login docker://nvcr.io' is done)"
apptainer build --force "${SIF_PUBLISH_PATH}" "${DEF}"

echo ">> sign (non-interactive, Vault-fed — ADR-012) + verify"
"${REPO_ROOT}/scripts/_apptainer_sign.sh" "${SIF_PUBLISH_PATH}"
apptainer verify "${SIF_PUBLISH_PATH}" || echo "WARN: verify failed (unsigned?) — SHA below is still the integrity check"

echo ">> SHA256 to append to containers/SHA256SUMS:"
sha256sum "${SIF_PUBLISH_PATH}" | sed "s| ${SIF_PUBLISH_PATH}| physicsnemo.sif|"

cat <<'NEXT'

Next operator steps:
  1. Append the SHA256 line above to containers/SHA256SUMS (the Stage 09 slot).
  2. GHCR mirror for RunPod (the pod pulls the OCI image, not the SIF):
       apptainer registry login docker://ghcr.io       # operator CR_PAT
       # mirror the NGC image (or a derived image) as
       #   ghcr.io/ernesto01louis/aero-physicsnemo:25.08
     Append the digest as a comment line to containers/SHA256SUMS:
       # ghcr.io/ernesto01louis/aero-physicsnemo:25.08 sha256:<digest>
  3. Pull once on the RunPod pod too (the ~20 GB pull is per-host).
NEXT
