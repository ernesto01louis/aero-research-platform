#!/usr/bin/env bash
# scripts/_apptainer_sign.sh — non-interactive Apptainer SIF signer (ADR-012).
#
# Fixes the Stage 07/08 failure where `apptainer sign` over SSH could not
# satisfy its TTY passphrase prompt (nekrs/jax-fluids/surrogate-smoke shipped
# UNSIGNED as a result). Feeds the signing-key passphrase — Vault-rendered — to
# `apptainer sign` via stdin (apptainer reads the passphrase from a non-TTY
# stdin), so SIF builds over SSH sign cleanly.
#
# Passphrase source (first found wins):
#   1. $APPTAINER_SIGN_PASSPHRASE env  (Vault-agent rendered; preferred)
#   2. /etc/aero/apptainer-signing.env  (Vault-agent rendered, mode 0600)
#   3. /root/.config/aero/signing.env   (Stage-02 interim location)
# If none is found, fall back to a normal interactive `apptainer sign` so a
# human at a TTY can still sign — NEVER silently skip signing.
#
# The signing key + passphrase are migrated into Vault in Stage 09 (ADR-012);
# the encrypted keyring escrow stays on the NAS at /mnt/aero/.keyring-escrow/
# (it rides the NAS ZFS migration — docs/runbooks/stage-09-nas-parallel-cutover.md).
#
# Usage: scripts/_apptainer_sign.sh <sif-path> [<key-index>]

set -euo pipefail

SIF="${1:?usage: _apptainer_sign.sh <sif-path> [key-index]}"
KEYIDX="${2:-0}"

_load_pass() {
  if [[ -n "${APPTAINER_SIGN_PASSPHRASE:-}" ]]; then
    printf '%s' "${APPTAINER_SIGN_PASSPHRASE}"
    return 0
  fi
  local f val
  for f in /etc/aero/apptainer-signing.env /root/.config/aero/signing.env; do
    if [[ -r "${f}" ]]; then
      val="$(grep -E '^(APPTAINER_SIGN_PASSPHRASE|SIF_PASSPHRASE)=' "${f}" | head -n1 | cut -d= -f2-)"
      if [[ -n "${val}" ]]; then
        printf '%s' "${val}"
        return 0
      fi
    fi
  done
  return 1
}

if PASS="$(_load_pass)"; then
  echo ">> signing ${SIF} (non-interactive, key ${KEYIDX})"
  printf '%s\n' "${PASS}" | apptainer sign --keyidx "${KEYIDX}" "${SIF}"
else
  echo "WARN: no Vault/file passphrase found — falling back to interactive sign" >&2
  apptainer sign --keyidx "${KEYIDX}" "${SIF}"
fi
