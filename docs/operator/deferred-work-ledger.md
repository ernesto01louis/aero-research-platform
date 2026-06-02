# Deferred-work ledger (as of Stage 09, 2026-06-01)

> Single source of truth for everything not-yet-done across Stages 01–09,
> grouped by **what unblocks it**. Born from the Stage-09 cleanup audit: the
> build is clean (zero design debt, all 9 CONSTITUTION invariants enforced, PR #14
> green), but the GPU + dedicated-NAS hardware is missing, so the remaining work
> is paced by hardware/cluster availability. This ledger keeps it visible.
>
> Per-stage detail lives in `docs/handoffs/STAGE-*-DONE-*.md`; decisions in
> `docs/adrs/`. Nothing here is "debt" — it's sequenced work waiting on a gate.

## 0. Host-side — operator-authorized cleanups (RESOLVED 2026-06-01)

Three clean-ups the auto-mode classifier (correctly) gated until explicit operator
sign-off, because they self-modify the agent's own controls / repo settings.
Operator approved; all three done:

- [x] **`.claude/hooks/block-dangerous-bash.sh`** no longer fails open without
  `jq` — it parses `tool_input.command` with `python3` (always present). Tested:
  `--no-verify`, `pct destroy`, and `ssh <shared-host> rm` all block (exit 2);
  benign + malformed input allow (exit 0).
- [x] **`.claude/rules/handoff-discipline.md`** + `docs/handoffs/_template.md`
  `model` field is now a placeholder (was hard-coded `claude-opus-4-7`).
- [x] **`non-commercial-fence` (check `fence`) promoted to a required status check
  on `main`** (8 required contexts now; the original 7 preserved). Verified via
  `gh api`. `provenance-completeness` deliberately NOT promoted (self-hosted
  runner — see §"Optional").

## 1. Phase 2 — build host / CPU cluster (aero-build, aero-vv; NO GPU/NAS)

Critical path: SIF builds unblock Phase 3.

- [ ] Apply the `aero-buildah-storage` Ansible role (graphroot → /mnt/pve/Storage)
  so the large SIF builds don't deadlock the root volume. `ansible/roles/aero-buildah-storage/`.
- [ ] Build SIFs on aero-build (scripts ready): `su2-v8` (Stage 06), `pyfr` +
  `nekrs` (Stage 07), `jax-fluids` + `surrogate-smoke` (Stage 08), `physicsnemo`
  (Stage 09 — NGC `physicsnemo:25.08`, ~20 GB pull, `apptainer remote login docker://nvcr.io`).
  Append each SHA to `containers/SHA256SUMS`.
- [ ] **Re-sign the unsigned SIFs** (nekrs, jax-fluids, surrogate-smoke) via
  `scripts/_apptainer_sign.sh` once the signing-key passphrase is Vault-rendered
  (ADR-012). Confirm signing doesn't churn the squashfs SHA.
- [ ] Migrate the Apptainer signing key + passphrase into Vault (ADR-012; the
  `aero-apptainer` role's vault-agent template). Escrow stays on the NAS.
- [ ] GHCR-mirror the SIFs (`ghcr.io/ernesto01louis/aero-*`) for RunPod pulls (CR_PAT).
- [ ] `uv pip install -e ".[provenance]"` on the aero-build/aero-dev venvs (dvc-s3)
  so DVC can push to the S3/MinIO remotes.
- [ ] SU2 + transonic cluster V&V validation runs → un-xfail
  `tests/vv/test_tmr_*_su2.py` + `test_transonic_naca0012.py` as cases pass (never
  relax tolerances).
- [ ] Confirm the `nvidia-physicsnemo` pip pin (proposed `1.1.0`) against the 25.08
  container; lock in ADR-010.
- [ ] **V&V reference-data digitization** (host-authorable once sources are in
  hand): Taylor-Green dissipation (Brachet 1983) → `data/references/scale_resolving/`,
  ONERA M6 Cp (Schmitt-Charpin) → `data/references/transonic/onera_m6/`. Until
  present, those cases raise `BenchmarkError`.

## 2. Phase 3 — GPU (RunPod) + data staging (operator-approved budget)

- [ ] Stage the DrivAerML subset to the `aero-cloud` RunPod network volume
  (conf/storage/cloud.yaml; the chosen cloud-now home).
- [ ] First paid H100 PyFR run (Taylor-Green; ~$0.62; cost-cap gated, Invariant 8).
- [ ] Smoke baselines (MLP/FNO/MGN) on RunPod via `aero surrogate train --executor runpod`.
- [ ] **DoMINO training** (`aero surrogate train --baseline domino --executor
  runpod --projected-hours <approved>`): multi-day H100 ≈ $67–191 → **exceeds the
  $50/mo cap; raise the per-run cap for this run**. Then: held-out Cd MAE p95 < 5%
  → `validated` cert + `surrogate_vv` report.
- [ ] NACA 0012 blunt-TE cluster mesh-sweep → confirm mesh VALID + Cd within 3% →
  un-xfail `tests/vv/test_tmr_naca0012.py` (the collapsed base-wake wedge may need
  iteration — see handoff §11).
- [ ] Then **tag `v0.0.9`** (Hard Rule 10 — handoff already exists).
- [ ] DrivAerNet++ lite manifest builder `_LAYOUT` population (after the first pull
  confirms the CSV columns); the full-mode (10.6 TB CFD) pull is NAS-gated.

## 3. Phase 4 — dedicated NAS (hardware purchase)

- [ ] Execute `docs/runbooks/stage-09-nas-parallel-cutover.md` (parallel cutover →
  re-IP, preserving 192.168.2.100; ZFS-replicate incl. the `.keyring-escrow`).
- [ ] Flip `conf/config.yaml` default `storage: cloud → nas`; verify a DVC
  round-trip against the TrueNAS-SCALE S3 app.
- [ ] Full-mode DrivAerNet++ + DrivAerML on-prem once capacity allows.

## 4. Future stages (10–16) — correctly scoped, NOT debt

- Stage 10: Transolver / FIGConvNet / X-MGN ensemble + MoE (reuse `aero/vv/surrogate/`).
- Stage 11: preCICE 3 FSI/CHT.
- Stage 12: DPW-7 / HLPW-5 / ERCOFTAC 3D V&V; ONERA M6 3D wing-slice; UQ envelope;
  periodic-hill pointwise profiles; the NACA-TE / flat-plate / bump V&V hardening
  to <5%.
- Stage 13: multi-cloud cost router (Lambda/Vast) + Postgres-backed ledger; adjoint
  shape-opt on JAX-Fluids `differentiable_run`.
- Stage 14: NeMo Agent Toolkit; the agent-side `cert.assert_current()` gate.
- Stage 15: literature mining (arXiv/Semantic Scholar/OpenAlex + pgvector); ORCID.
- Stage 16: JOSS submission; Zenodo per-release DOI; license-scan CI.

## Optional / low-priority

- Promote `provenance-completeness` to a required check **only** once the
  self-hosted `vv` runner is reliably online (a required check on an offline
  runner blocks all PRs — why it's currently gated).
- Decide the non-root `apptainer exec` posture (run-as-root vs privileged LXC) —
  document in an ADR (Stage-02 §6; not blocking).
