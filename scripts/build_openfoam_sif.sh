#!/usr/bin/env bash
# scripts/build_openfoam_sif.sh
#
# Stage 03 — build, sign, and publish the OpenFOAM-ESI solver SIF.
# Runs ON aero-build as root (Stage 02 precedent: SIFs build as the LXC root;
# non-root apptainer exec fails in the unprivileged LXC).
#
# Builds, signs, verifies, and publishes:
#   openfoam-esi.sif — OpenFOAM-ESI v2412, FROM the digest-pinned upstream image
# to /mnt/aero/containers/ (the TrueNAS NFS dataset), then prints the SHA256
# line to record in containers/SHA256SUMS.
#
# Prerequisites: Apptainer installed; host `fuse` module loaded; the TrueNAS
# aero/ export bind-mounted at /mnt/aero; the Stage 02 signing keypair present
# (scripts/build_base_sifs.sh generated it); openfoam-esi.def in <def-dir>.
#
# Usage (on aero-build, as root):  ./build_openfoam_sif.sh [def-dir]
#                                  (default def-dir: /tmp)

set -euo pipefail

DEFDIR="${1:-/tmp}"
SIF="openfoam-esi.sif"
DEF="openfoam-esi.def"
CONTAINERS="/mnt/aero/containers"
PASSFILE="/root/.config/aero/signing.env"

log() { echo "[build-openfoam-sif] $*"; }

command -v apptainer >/dev/null || { echo "apptainer not installed" >&2; exit 1; }
[ -f "${DEFDIR}/${DEF}" ] || { echo "${DEFDIR}/${DEF} not found" >&2; exit 1; }
[ -f "$PASSFILE" ] || { echo "$PASSFILE absent — run build_base_sifs.sh first" >&2; exit 1; }

# shellcheck disable=SC1090
source "$PASSFILE"

log "building ${SIF} (FROM digest-pinned opencfd/openfoam-default:2412)"
apptainer build --force "${DEFDIR}/${SIF}" "${DEFDIR}/${DEF}"

log "signing ${SIF}"
echo "$AERO_SIGNING_PASSPHRASE" | apptainer sign "${DEFDIR}/${SIF}"
apptainer verify "${DEFDIR}/${SIF}"

mkdir -p "$CONTAINERS"
cp "${DEFDIR}/${SIF}" "$CONTAINERS/"
log "published to ${CONTAINERS}/${SIF}"

echo
log "SHA256 (record this line in containers/SHA256SUMS):"
(cd "$CONTAINERS" && sha256sum "$SIF")
