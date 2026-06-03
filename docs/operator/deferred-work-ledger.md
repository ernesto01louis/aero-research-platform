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

**Phase 2 COMPLETE (2026-06-02/03)** — ran on aero-build + the DrivAerML pull:
- [x] `physicsnemo.sif` built (apptainer-direct from NGC 25.08) + **signed**; SHA
  recorded. (The other 5 SIFs already existed from Stages 06–08.) Pin confirmed +
  bumped to `nvidia-physicsnemo==1.2.0` (ADR-010 amendment); redundant `%post` pip dropped.
- [x] **All SIFs signed + verified** (`apptainer verify`, 2026-06-03): nekrs,
  physicsnemo, jax-fluids, surrogate-smoke, pyfr, su2-v8, openfoam-esi — chain
  complete. (jax-fluids + surrogate-smoke re-signed; the rest were already signed —
  the Stage-09 "nekrs unsigned" audit note was WRONG. The signer's
  `AERO_SIGNING_PASSPHRASE` bug was fixed.)
- [x] DrivAerML surface subset pulled: **484 runs, ~353 GiB (STL + boundary VTP)**,
  DVC-tracked on the new `aero-nfs` local remote (`/mnt/aero/dvc-remote`).
- [x] Build scratch via `APPTAINER_CACHEDIR/TMPDIR` on local disk (physicsnemo is
  apptainer-direct — no buildah; apply `aero-buildah-storage` before any future
  buildah two-step SIF).

Deferred from Phase 2 (not build-blocking):
- [ ] **Vault signing-key migration** — signing works via the Stage-02 interim
  `signing.env`; migrate to Vault when convenient (ADR-012).
- [ ] **GHCR mirror** — optional; physicsnemo:25.08 is a public NGC image (see the
  Phase-3 runbook Step 2 for the image/registry-auth choice).
- [ ] `dvc[s3]` on the venvs — only for Phase-3 *cloud* staging (the on-prem pull
  used a local remote).

Separate **V&V-hardening** track (CPU cluster; NOT a build task — was mis-bucketed here):
- [ ] SU2 + transonic cluster V&V → un-xfail `tests/vv/test_tmr_*_su2.py` +
  `test_transonic_naca0012.py` as cases pass (never relax tolerances).
- [ ] V&V reference-data digitization: Taylor-Green dissipation (Brachet 1983),
  ONERA M6 Cp (Schmitt-Charpin). Until present those cases raise `BenchmarkError`.

## 2. Phase 3 — GPU (RunPod) + data staging (operator-approved budget)

> **Turnkey procedure: `docs/runbooks/stage-09-phase-3-domino-training.md`** — the
> real PhysicsNeMo 1.2.0 DoMINO API + the `PhysicsNeMoDominoEngine` wiring spec +
> image/registry-auth + data staging + the training command + post-run un-xfail/tag.

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
