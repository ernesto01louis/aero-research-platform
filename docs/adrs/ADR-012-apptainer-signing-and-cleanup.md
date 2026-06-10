# ADR-012 — Non-interactive Apptainer signing + Vault-managed key (Stage-09 cleanup)

- **Status:** accepted
- **Date:** 2026-06-01
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09

## Context and problem statement

`apptainer sign` prompts for the signing-key passphrase via the TTY. In a
non-interactive SSH session (`scripts/build_*_sif.sh` driving a build over SSH to
`aero-build`), the prompt fails — so nekrs (Stage 07), jax-fluids and
surrogate-smoke (Stage 08) all shipped **UNSIGNED**, while `containers/SHA256SUMS`
still claimed "All SIFs are signed". The four-fold provenance tuple records the
SIF *hash* (so reproducibility is intact), but the signature trust-chain is
broken, and PhysicsNeMo (Stage 09) would hit the same gate. The operator asked to
"make the build as clean as it can be — fix what we skipped." This ADR records the
signing fix + two small adjacent cleanups.

## Decision drivers

- **Provenance integrity** (Principle 1, Invariant 3) — signed SIFs complete the
  trust chain the SHA alone can't.
- **No secrets in the repo** (Hard Rule 7) — the passphrase lives in Vault.
- **DOCS MATCH REALITY** (Hard Rule 9) — the manifest must stop lying.
- **Security posture** — a passphrase-less key weakens at-rest protection the
  on-NAS escrow already assumes.

## Considered options (signing)

1. **Vault-fed passphrase, piped non-interactively** to `apptainer sign` via a
   `scripts/_apptainer_sign.sh` helper; migrate the key into Vault.
2. **Passphrase-less CI signing key** (no prompt, but unencrypted at rest).
3. **Sign in person at PR-merge time** (status quo deferral).

## Decision outcome

Chose **Option 1** because it keeps the existing encrypted keyring + escrow
posture while making signing work over SSH/CI — the build scripts can sign
unattended without weakening the key.

### Key decisions

- **`scripts/_apptainer_sign.sh`** reads the passphrase (first found:
  `$APPTAINER_SIGN_PASSPHRASE` → `/etc/aero/apptainer-signing.env` →
  `/root/.config/aero/signing.env`) and pipes it to `apptainer sign` via non-TTY
  stdin. If no passphrase is found it falls back to an interactive sign — never
  silently skips. `build_{physicsnemo,jax_fluids,surrogate_smoke}_sif.sh` call it.
- **Key migration into Vault:** the signing key + passphrase move into Vault
  (`secret/aero/apptainer-signing`), rendered to `aero-build` by the
  `aero-apptainer` Ansible role's vault-agent template. The encrypted keyring
  escrow stays at `/mnt/aero/.keyring-escrow/` and **rides the NAS ZFS migration**
  (`docs/runbooks/stage-09-nas-parallel-cutover.md`) — sequence the escrow copy to
  survive the cutover before retiring the on-host key.
- **Doc-drift corrected:** `containers/SHA256SUMS` header now states the truthful
  signing state; `SECURITY.md` corrected ("Vault stood up Stage 04"; the key
  migration is Stage 09).
- **Re-sign outstanding SIFs:** nekrs, jax-fluids, surrogate-smoke are re-signed
  on the next build-host pass (operator step). Signing does not change the
  squashfs SHA256 (verify on-box; if it does, SHA256SUMS churns).

## Related cleanup: DrivAerNet++ `body_length` (option 3)

The lite-mode `DrivAerNet_ParametricData.csv` `A_Car_Length` is a **signed delta**
from an undocumented DrivAer baseline (values include negatives), so the loader's
`body_length_m: float = Field(..., gt=0.0)` rejected it. **Chose option 3**: rename
`body_length_m → body_length_param` (sign-neutral, drop `gt=0.0`) — the only
data-independent fix; it unblocks the lite schema without recovering the baseline
or pulling the 443 GB 3D-Meshes. DoMINO trains on DrivAerML (not DrivAerNet++), so
this is pure debt-paydown. `dvc.yaml`'s `ingest-drivaernet-plus-plus` drops the
not-yet-buildable `manifest.json` out (the lite manifest builder is still a pending
`_LAYOUT` entry).

## Consequences

- **Positive:** SIFs sign unattended; the manifest tells the truth; the signing
  key gains Vault custody; the lite DrivAerNet++ schema validates.
- **Negative:** the exact stdin-pipe behavior is apptainer-version-dependent —
  validated on the first build-host signing pass (cluster-gated); `expect` is the
  documented fallback.
- **Neutral / followup:** confirm re-signing doesn't churn the SIF SHAs.

## Links

- Stage prompt: `STAGE-09-domino-baseline-surrogate.md`
- Related ADR: ADR-002 (Stage-02 signing interim), ADR-004 (Vault), ADR-010 (DoMINO SIF)
- Related: `SECURITY.md` §6, `docs/runbooks/stage-09-nas-parallel-cutover.md`
