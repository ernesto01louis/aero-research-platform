# Deferred-work ledger (as of Stage 09, 2026-06-01; refocused 2026-06-10)

> Single source of truth for everything not-yet-done across Stages 01–09,
> grouped by **what unblocks it**. Born from the Stage-09 cleanup audit: the
> build is clean (zero design debt, all 9 CONSTITUTION invariants enforced, PR #14
> green), but the GPU + dedicated-NAS hardware is missing, so the remaining work
> is paced by hardware/cluster availability. This ledger keeps it visible.
>
> Per-stage detail lives in `docs/handoffs/STAGE-*-DONE-*.md`; decisions in
> `docs/adrs/`. Nothing here is "debt" — it's sequenced work waiting on a gate.
>
> **⚠ Optimizer-mission refocus (ADR-013, 2026-06-10).** The platform is now an
> aerodynamic shape optimizer (flapping flagship). The automotive surrogate path is
> **cut**: §2 DoMINO training is CANCELLED (struck through below, kept for the record);
> §4's old Stage 10–16 list is replaced by the Stage 10–20 map in
> `docs/handoff-bundle/README-handoff.md`. Frozen artifacts (DoMINO code,
> `physicsnemo.sif`, the 353 GiB DrivAerML subset) stay in place — **disk reclaim is a
> NEW propose-first item (§5) requiring literal `approved`.**

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

## 0b. Stage-12 CI required-check promotions (RESOLVED 2026-07-06, recorded Stage 13)

Stage 12 (ADR-020) added the two CONSTITUTION-invariant gates and (per the Stage-12
handoff §5) they were to be promoted to required checks after the Stage-12 PR merged.
**Both are now required** — verified via `gh api .../branches/main/protection/required_status_checks/contexts`
at the Stage-13 start (10 required contexts):

- [x] **`small-signal-gate — Invariant 10`** (IMPROVEMENT-EXCEEDS-UNCERTAINTY) — required,
  `ubuntu-latest` (runner-independent → required-safe).
- [x] **`data-origin-fence — Invariant 11`** (NO-SURROGATE-ON-FOREIGN-DATA) — required,
  `ubuntu-latest`.

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

**CANCELLED per ADR-013 (2026-06-10) — struck through, kept for the record:**
- ~~Stage the DrivAerML subset to the `aero-cloud` RunPod network volume.~~
- ~~Smoke baselines (MLP/FNO/MGN) on RunPod.~~
- ~~**DoMINO training** (multi-day H100 ≈ $67–191).~~ *(automotive path cut; no spend.)*
- ~~DrivAerNet++ lite manifest builder `_LAYOUT` population; full-mode (10.6 TB) pull.~~

**SURVIVES — moved to Stage 10 (V&V debt go/no-go):**
- [ ] **NACA 0012 blunt-TE cluster mesh-sweep** → confirm mesh VALID + Cd within 3% →
  un-xfail `tests/vv/test_tmr_naca0012.py` (the collapsed base-wake wedge may need
  iteration — see handoff §11). *(Was mis-coupled to the surrogate stage; it is
  V&V-hardening. Now a Stage-10 deliverable.)*

**Optional infra-validation (demoted; not on the optimizer path):**
- [ ] First paid H100 PyFR run (Taylor-Green; ~$0.62) — only as a cloud-path liveness
  check if/when a GPU run is needed; smoke runs are Invariant-11-exempt.

**Tag:** v0.0.9 is recommended at the Stage-09 close-out (handoff §14) on the operator's
literal `approved` — no longer gated on training evidence.

## 3. Phase 4 — dedicated NAS (hardware purchase)

- [ ] Execute `docs/runbooks/stage-09-nas-parallel-cutover.md` (parallel cutover →
  re-IP, preserving 192.168.2.100; ZFS-replicate incl. the `.keyring-escrow`).
- [ ] Flip `conf/config.yaml` default `storage: cloud → nas`; verify a DVC
  round-trip against the TrueNAS-SCALE S3 app.
- [ ] Full-mode DrivAerNet++ + DrivAerML on-prem once capacity allows.

## 4. Future stages (10–20) — see the re-aimed map

The original Stage 10–16 list (automotive zoo, DPW/HLPW, multi-cloud router, NeMo agent,
literature miner) is **superseded by ADR-013.** The current map is
`docs/handoff-bundle/README-handoff.md` (Stage 10–20): V&V debt go/no-go → moving-mesh +
unsteady → UQ core → transition → rigid flapping → **parametric optimization (thesis
checkpoint)** → surrogate-accelerated optimization → geometry ingestion → preCICE FSI →
flexible flapping → flexible-flapping optimization + v0.1.0. **Deferred indefinitely:** NeMo
agent layer, literature miner, MoE, DPW/HLPW, riblet DNS.

## 5. NEW — propose-first / acquisition items (post-refocus)

- [ ] **DrivAerML ~353 GiB disk reclaim** — propose-first, requires literal `approved`.
  The 484-run subset on the `aero-nfs` remote is frozen (ADR-013); ~369 GB free on TrueNAS,
  so there is real pressure, but removal touches `SHA256SUMS`/DVC and is not automatic.
- [ ] **Flapping reference-data acquisition** (DVC-tracked under `data/reference/`, per
  owning stage): McCroskey + Heathcote-Gursul → Stage 13; Dickinson + Wang-Birch-Dickinson
  → Stage 14; Turek-Hron tabulated → Stage 18; Blasius / low-Re cylinder Strouhal → Stage 10.
- **Post-v0.1.0 named sequence (committed, further out):** adjoint shape/topology
  optimization (DAFoam v5 + SU2 adjoint — SU2 frozen-optional, re-activated here) →
  generative / true-topology proposers.

## Optional / low-priority

- Promote `provenance-completeness` to a required check **only** once the
  self-hosted `vv` runner is reliably online (a required check on an offline
  runner blocks all PRs — why it's currently gated).
- Decide the non-root `apptainer exec` posture (run-as-root vs privileged LXC) —
  document in an ADR (Stage-02 §6; not blocking).
