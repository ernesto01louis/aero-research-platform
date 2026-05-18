#!/usr/bin/env bash
# scripts/build_base_sifs.sh
#
# Stage 02 — build, sign, and publish the aero base Apptainer SIFs.
# Runs ON aero-build as root. Regenerates the signing keypair only if absent.
#
# Produces, signs, verifies, and SHA256-records:
#   _base.sif       — pinned Ubuntu 24.04 base image
#   hello-world.sif — trivial test image (bootstrapped FROM _base.sif)
# then publishes them to /mnt/aero/containers/ (the TrueNAS NFS dataset) and
# escrows the keyring to /mnt/aero/.keyring-escrow/.
#
# Prerequisites (Stage 02): Apptainer installed (ansible aero-apptainer role);
# the host `fuse` module loaded; the TrueNAS aero/ export bind-mounted at
# /mnt/aero; the .def files present in <def-dir>.
#
# Usage (on aero-build):  ./build_base_sifs.sh [def-dir]   (default /tmp)
#
# After running, copy the printed sha256 lines into containers/SHA256SUMS
# and the key fingerprint into containers/SIGNING_KEY_FINGERPRINT.txt.

set -euo pipefail

DEFDIR="${1:-/tmp}"
CONTAINERS="/mnt/aero/containers"
ESCROW="/mnt/aero/.keyring-escrow"
PASSFILE="/root/.config/aero/signing.env"
KEYNAME="aero-research-platform"
KEYEMAIL="aero@aero-research-platform.local"
KEYCOMMENT="Stage 02 container signing key"

log() { echo "[build-sif] $*"; }

command -v apptainer >/dev/null || { echo "apptainer not installed" >&2; exit 1; }

# --- signing keypair (generate once, passphrase-protected) ---
if ! apptainer key list 2>/dev/null | grep -q Fingerprint; then
  log "generating signing keypair"
  mkdir -p "$(dirname "$PASSFILE")" && chmod 700 "$(dirname "$PASSFILE")"
  pass="$(openssl rand -base64 24)"
  printf 'AERO_SIGNING_PASSPHRASE=%s\n' "$pass" >"$PASSFILE"
  chmod 600 "$PASSFILE"
  apptainer key newpair --name "$KEYNAME" --email "$KEYEMAIL" \
    --comment "$KEYCOMMENT" --password "$pass" --push=false
fi
# shellcheck disable=SC1090
source "$PASSFILE"

# --- build ---
log "building _base.sif"
apptainer build --force "${DEFDIR}/_base.sif" "${DEFDIR}/_base.def"
log "building hello-world.sif (FROM _base.sif)"
(cd "$DEFDIR" && apptainer build --force hello-world.sif hello-world.def)

# --- sign + verify ---
for sif in _base.sif hello-world.sif; do
  log "signing $sif"
  echo "$AERO_SIGNING_PASSPHRASE" | apptainer sign "${DEFDIR}/${sif}"
  apptainer verify "${DEFDIR}/${sif}"
done

# --- publish to the NFS container library ---
mkdir -p "$CONTAINERS"
cp "${DEFDIR}/_base.sif" "${DEFDIR}/hello-world.sif" "$CONTAINERS/"
log "published to $CONTAINERS"

# --- escrow the keyring (pgp-secret is passphrase-encrypted at rest) ---
mkdir -p "$ESCROW" && chmod 700 "$ESCROW"
cp /root/.apptainer/keys/pgp-public /root/.apptainer/keys/pgp-secret "$ESCROW/"
chmod 600 "$ESCROW"/*
log "keyring escrowed to $ESCROW"

echo
log "SHA256 (record these in containers/SHA256SUMS):"
(cd "$CONTAINERS" && sha256sum _base.sif hello-world.sif)
log "key fingerprint (record in containers/SIGNING_KEY_FINGERPRINT.txt):"
apptainer key list 2>/dev/null | awk '/Fingerprint/ {print $2}'
