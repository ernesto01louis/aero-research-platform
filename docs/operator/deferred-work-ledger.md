# Deferred-work ledger (as of Stage 09, 2026-06-01; refocused 2026-06-10; refreshed Stage 21, 2026-10-12)

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

**Fixed Stage 13:** `data-origin-fence` was **path-filtered** to `aero/surrogates/**`, so as a
*required* check it left its context unreported on any PR not touching surrogate paths — blocking
the merge indefinitely (hit on the Stage-13 PR, the first non-surrogate PR after Invariant 11
became required). Removed the path filter so the fast pure-host fence runs on every PR (matching
the un-filtered `small-signal-gate`). A required constitutional invariant should verify on every
change regardless.

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
  → Stage 14; **Turek-Hron tabulated → CLOSED at Stage 18** (geometry + CFD1/2/3 values,
  `data/references/fsi/turek_hron_fsi3/`; the FSI3 *displacement* data is Stage 19's);
  Blasius / low-Re cylinder Strouhal → Stage 10.
- **Post-v0.1.0 named sequence (committed, further out):** adjoint shape/topology
  optimization (DAFoam v5 + SU2 adjoint — SU2 frozen-optional, re-activated here) →
  generative / true-topology proposers.

## 6. NEW — audit-ledgered items (2026-07-10, ADR-025)

From the 2026-07 external-audit reconciliation (`docs/review/2026-07-audit-reconciliation.md`);
the adopted-now items landed as the ADR-025 anti-surrogate-exploitation stack. These are the
explicitly-deferred remainders, each with its unblocking condition:

- [ ] **MC-dropout uncertainty basis** — the `basis` Literal in `SurrogatePrediction` /
  `UncertaintyCalibration` reserves `"mc_dropout"`; a producer needs member-internal dropout
  support (torch-side). Unblocked by: a Stage-16+ member architecture that wants it (deep
  ensembles are the default; ADR-025 option c).
- [ ] **Anisotropic (per-dimension) trust-region radii** — `TrustRegionState.radius` is a
  scalar L-infinity half-width. Unblocked by: Stage-16 evidence that design variables have
  wildly different objective sensitivities.
- [ ] **Std recalibration (temperature scaling)** — if a Stage-16 ensemble's held-out
  coverage drifts outside the promotion band, rescale stds on the calibration split rather
  than discarding the ensemble. Unblocked by: observed miscalibration in a real campaign.
- [ ] **Differentiable trilinear FFD (PyTorch)** — enables gradient-based optimization
  through a differentiable surrogate (audit item 10). Premature for Stage 15's ≈2–6-var BO;
  natural entry at Stage 16+ or with the post-v0.1.0 adjoint sequence (§5).
- [ ] **Generic external-aero autogen template** (arbitrary-STL domain sizing, BCs,
  snappyHexMesh/cfMesh, k-ω SST, y+ strategy, forceCoeffs) — the audit's "self-generated
  CFD factory" for arbitrary geometry families. Owned by **Stage 18 post-renumbering**.
  **Progress (Stage 18):** the STL→ingestion-gate→snappy→checkMesh-gate→forceCoeffs
  pipeline exists for quasi-2D channel cases (`ExternalGeometrySpec`, ADR-033/034).
  Open remainder: 3D domain auto-sizing, external-aero BC templates, turbulence/y+
  strategy selection (the Stage-18 anchor is laminar).
- [ ] **SU2 adjoint classical-ASO benchmark** — audit item 13; already the committed
  post-v0.1.0 sequence in §5 (DAFoam v5 + SU2 adjoint). Cross-referenced, not duplicated.

## Stage 17 (surrogate-accelerated optimization) — carried forward

- [ ] **Fair-test surrogate-speed-up experiment (reduced prior / higher-DV)** — the Stage-17
  pre-registered speed-up comparison was DEGENERATE: the 42-solve own-CFD corpus already
  contained designs past the +22.2 bar, so the surrogate arms did 0 marginal search while
  direct-CFD BO reached the bar from scratch in 4–7 evals. The meaningful test trains the
  surrogate on a prior that does NOT already solve the problem (exclude the past-bar region)
  and/or moves to a higher-DV space where direct BO is not already ~5-eval-efficient, giving
  the surrogate genuine acceleration headroom. Unblocked by: Stage 18 arbitrary-geometry /
  higher-DV shape spaces.
- [ ] **Balanced flywheel growth / corpus curation** — re-training on `corpus_v2` (base + 16
  exploit-clustered exploratory infill points) REFUSED promotion (held-out ld_mae p95 2.62 >
  2.5): exploit-heavy growth over-concentrates the training distribution and degrades global
  calibration. A curation policy (explore/exploit ratio, coverage-preserving subsampling, or
  down-weighting clustered near-optimum points) should govern how infill grows the certified
  corpus. Unblocked by: a stage that runs the loop long enough to accumulate real infill.
- [ ] **Content-addressed dataset hash** — `dataset_hash` is a DVC *sync-state* fingerprint
  (`dvc status -c`), so it detects out-of-sync tracked state, not corpus content, and the
  in-loop Invariant-9 data gate is near-tautological when the cert is re-issued every
  iteration against the same file. A content hash (sha256 of the corpus bytes) would make the
  data gate detect content tampering. Unblocked by: none — a small, self-contained change.
- [ ] **Direct-arm evals into the corpus** — `EvalRow` (speed-up traces) does not carry the
  four-fold provenance tuple, so only surrogate-loop evals flow into `corpus_v2`; the direct
  arms' 16 own-CFD solves are stranded in their bundles. Thread the four-tuple through
  `EvalRow` so every own-CFD eval can join the flywheel.

## Stage 18 (arbitrary-geometry ingestion) — carried forward

- [ ] **Promote the mesh fallback ladder into the V&V runner** — `aero vv run` executes
  external-geometry cases single-shot (`OpenFOAMSolver.mesh`, no ladder, no checkMesh
  gate); the ladder lives in the campaign driver (`mesh_with_ladder`). Promotion means
  `BenchmarkRunner._drive` (or a mesh-strategy seam) gates every V&V mesh. ADR-034
  Consequences. Unblocked by: none — a contained refactor.
- [ ] **Vertex-manifoldness (bowtie) check** in `aero/geometry/quality.py` — v1 checks
  edge-manifoldness + orientation + intersections (the mesher-relevant modes); a
  bowtie vertex (two fans sharing only a vertex) passes. ADR-033 Consequences.
- [ ] **3D (non-slab) external-geometry mode** — `ExternalGeometrySpec` is quasi-2D
  (one-cell slab); 3D needs volumetric refinement levels (breaking the slab trick),
  layer strategy, and a mesh-cost budget model. Needed by the flapping-wing geometry
  on-ramp.

## Optional / low-priority

- Promote `provenance-completeness` to a required check **only** once the
  self-hosted `vv` runner is reliably online (a required check on an offline
  runner blocks all PRs — why it's currently gated).
- Decide the non-root `apptainer exec` posture (run-as-root vs privileged LXC) —
  document in an ADR (Stage-02 §6; not blocking).

## Stage 19 (preCICE FSI core) — new items

- **Stage-11 moving-mesh PSS gate: enable the cumulative bound (needs discard-first).**
  The cumulative linear-trend bound now lives in the shared
  `aero/postprocess/cycle_detection.py` (ADR-019 amendment, Stage 19) and is COMPUTED and
  reported by `_load_moving` / `_load_flapping`, but those paths do NOT gate on it.
  Reason, measured: they segment from t=0 and let the adjacent-drift scan pick the tail,
  which can include transient cycles; re-analysing 107 surviving historical runs with the
  bound enabled flipped 56, and real drift could not be separated from that artifact.
  Enabling it safely requires adopting Stage-19's unconditional-discard-then-analyze
  discipline first (discard the start-up transient, THEN segment + gate), which changes
  tail selection and hence historical verdicts. Do it per-owning-stage (11/13/14) with
  re-runs of the affected cases; the surviving force histories are under
  `/mnt/aero-nfs/runs/{plunging_airfoil_hg2007,oscillating_cylinder_lockin}-*`.
- ~~**CalculiX SIF not built.**~~ **CLOSED in Stage 20 (`bc1384a`).** `calculix-precice.sif`
  was built, then rebuilt on calculix-adapter v2.20.2; `calculix-precice-adr045.sif` is the
  solid container of record. Both digests are in `containers/SHA256SUMS`.
- **The `aero[precice]` extra is exercised only inside the SIF** (by `solverdummy`). If a
  host-side in-process participant ever lands, revisit what the extra is for.
- **`_txt_table` treats any short final row as a partial write.** Correct for a live
  preCICE file; a file truncated by something else would read as one silently dropped row.
- ~~**The README STATUS generator cannot express "stage complete, not yet tagged"**~~
  **CLOSED in Stage 20 (`40503e6`).** The generator now writes "(not yet tagged)" when the
  handoff's `stage_tag` does not exist.

## Stage 20 (flexible flapping FSI) — NO-GO on infrastructure; carried by ADR-046

- **Flexible-flapping optimization is DEFERRED past v0.1.0** (ADR-046 S4). It re-enters only
  under S5: a NEW ADR that names the infrastructure fix, plus the operator's word. No Stage-20
  lever is retried, and the four B-sentinels stay permanently unfilled.
- **`moving-vv` is known-failing** (ADR-049 H-20). Its last five scheduled runs (2026-09-13 to
  2026-10-11) failed. The latest is `plunging_airfoil_hg2007` timing out at the 14 400 s
  `run_long.sh` ceiling (`pimpleFoam` rc=124). Raising the ceiling, or a compute fix, is the
  operator's decision (O-16). Only read-only triage of the run logs is in scope.
  **Stage 23 (2026-10-21):** from 2026-10-18 the job stopped measuring at all. The Stage-21 H-09
  dispatch-input guard (`f52c5b3`, #49) refused the empty input of every scheduled run in ~14 s
  (run 39105845993). Stage 23's first PR validates the input as one string; the job is expected
  to fail honestly again on `plunging_airfoil_hg2007`'s 14 400 s ceiling, with the cylinder
  measured (operator, 2026-10-21: keep both default cases).
- **Stage 18–20 records are not crated at v0.1.0** (O-22). A later ADR can crate them additively.

## Stage 21 (release) — OUT list and findings

The closed hardening list is in ADR-049 R4. These are OUT, with their destinations:

| ID | Item | Why out / destination |
|---|---|---|
| O-01 | Stage-11 PSS S3/S5 backfill | needs re-runs |
| O-02 | Mesh fallback ladder / checkMesh gate in the V&V runner | behaviour change; needs cluster verification (Stage 18 item above) |
| O-03 | Bowtie vertex check | new quality gate (Stage 18 item above) |
| O-04 | 3-D external geometry | feature (Stage 18 item above) |
| O-05 | Fair-test speed-up | new campaign (Stage 17 item above) |
| O-06 | The 393² rung (Stage-17 thesis-grade) | 10–14 days of compute |
| O-07 | Content-addressed `dvc_input_hash` | changes four-tuple semantics; post-v0.1.0 ADR |
| O-08 | Re-hash the SIF at launch | cluster code path; documented in SECURITY.md and every crate |
| O-09 | RunPod `StrictHostKeyChecking=no` | frozen GPU path; documented in SECURITY.md |
| O-10 | Claude hook changes (Stop-hook path via `$CLAUDE_PROJECT_DIR`; fail-closed Bash hook) | operator-only |
| O-11 | PyPI (`aero` is taken; the jaxfluids git reference blocks upload) | distribution-name ADR |
| O-12 | A docs site | operator choice; SCOPE-GATE |
| O-13 | Backfilled Releases v0.0.8–v0.0.20, or a v0.0.5 tag | would mint stale-metadata DOIs |
| O-14 | Container-image licence scan / SBOM | outside the Python lock |
| O-15 | A full Python 3.13 test leg | only the crate reader runs on 3.13 |
| O-16 | A `moving-vv` compute fix | no compute this stage |
| O-17 | `enforce_admins` | deadlocks with a sole code owner; `release_readiness.py --online` substitutes |
| O-18 | Platform markers on the jax-fluids NVIDIA wheels | frozen GPU extra |
| O-19 | actionlint / zizmor | the workflow-hygiene test covers the key rules |
| O-20 | A coverage threshold | — |
| O-21 | Stage-13 crates | schema drift; refused by the legacy import, never "fixed" |
| O-22 | Crates for Stages 18–20 | additive ADR later |
| O-23 | Re-certifying the Stage-17 surrogate | compute. The certificate expires 2027-01-20 and every crate states it. |
| O-24 | Ephemeral runners, CodeQL, tag rulesets | operator settings |

New findings during Stage 21 (not release-blocking):

- [ ] **pip-audit reports known advisories in the locked versions.** On 2026-10-12: 161
  advisories across 20 packages, mostly transitive (aiohttp, anyio, asyncssh, cryptography,
  diskcache, dulwich, fsspec, gitpython, hydra-core, mlflow, multidict, pillow, pyasn1,
  pydantic-settings, setuptools, sqlparse, starlette, urllib3, virtualenv, werkzeug). A lock
  refresh is its own change: re-run the licence `refresh`, re-verify, and run a FULL vv-required.
  The job is informational (`dependency-licences.yml`).
- [ ] **The external RO-Crate validator's Process Run Crate profile is still 0.5** (RO-Crate 1.1),
  so the PRC 0.6 MUSTs are checked in-repo (`aero/crate/conformance.py`). Re-check when
  roc-validator ships PRC 0.6.
- [ ] **H-34: path-safe preCICE directory fields** (ADR-049 P2, not done at Stage 21).
  - Add a simple-name pattern (no `.`/`..`, only `[A-Za-z0-9._-]`) to the workdir / tutorial /
    participant-dir fields in `aero/adapters/precice/case.py`, and `shlex.quote` at the
    solver's shell line.
  - Every committed value is a simple name, so `config_hash` is unchanged.
  - It touches `aero/adapters/**`, so it needs a FULL vv-required run.
- [ ] **H-35: 3MF zip caps** (ADR-049 P2, not done at Stage 21). In `aero/geometry/threemf.py`:
  - at most 10 000 entries;
  - at most 512 MiB per part;
  - a compression ratio of at most 200;
  - refuse `..` and absolute member names.

  It touches `aero/geometry/**`, so it needs a FULL vv-required run.
- [x] **`scripts/regenerate_status.sh` has no unit test** for complete-untagged, complete-tagged or
  an empty `next_stage`. It is exercised only by the required docs-sync job. **Done in Stage 22**
  (ride-along): `tests/unit/test_regenerate_status.py` covers all three, plus partial/blocked,
  the lexicographic pick, `--check` drift and the bootstrap message.
- [x] ~~CONSTITUTION Invariant 8's `default 50.0` parenthetical~~ (noted at Stage 10). This was
  already fixed: Invariant 8 reads `default 150.0`, raised from 50.0 by ADR-014. Nothing to carry.

## Stage 22 (an honest V&V report) — findings carried forward

Found by the Stage-22 workflow audit (ADR-051 deliverable 4). Stage 22 makes each of them
visible; it fixes none of the physics or solver problems.

- [ ] **SU2_CFD dies at startup on `aero-build` for every case** ("solver failed (rc=1)"; the
  2D bump through SU2 uses an analytic mesh and fails the same way, so it is not the ONERA mesh).
  **Diagnosed by the Stage-22 dispatch (run 38891472030):** `MPI_Init` fails with
  `mca_bml_base_open() failed` / "Not found" for framework `btl`, component `sm`. The SU2 SIF ships
  Open MPI 4.1.6, whose shared-memory BTL is `vader` (`ompi_info` lists `ofi, openib, self, tcp,
  vader`), so the adapter's Stage-06 override `OMPI_MCA_btl=self,sm`
  (`aero/adapters/su2/solver.py`) names a component that does not exist. Likely fix:
  `self,vader`, verified by a `vv-transonic` dispatch before it is believed (a FULL `vv-required`
  run, since it touches `aero/adapters/**`). SU2 is frozen-optional (ADR-013), so this is fixed
  only if the operator invests in the SU2 stack.
- [ ] **`OneraM6.evaluate()` always raises**: the eta = 0.44 chordwise Cp slice on the 3D wing
  surface is unimplemented (`aero/vv/transonic/onera_m6.py`). The case cannot pass or fail on a
  real comparison until it exists. SU2 stack, frozen-optional.
- [ ] **A failed solve logs nothing to MLflow.** `BenchmarkRunner._drive` raises before `_log`, so
  the report cannot show a crash: the case keeps its last logged status (or `missing`). Decide in
  Stage 24 whether a failed solve becomes a logged `fail` with the error as an artifact.
- [ ] **`bump_2d` has no single-grid V&V test** (`tests/vv/test_tmr_bump_2d.py` holds only the GCI
  sweep), so it has 369 `-sweep` runs and no gated run. Stage 24.
- [ ] **The bump GCI sweep XPASSed** on the 2026-10-15 nightly (`xfail(strict=False)`). Whether its
  documented convergence concern still holds is Stage 25's question; the marker was not touched.
- [ ] **`vv-scale-resolving` names two test files that never existed**
  (`tests/vv/test_taylor_green_{pyfr,nekrs}.py`), and no `gpu` runner exists. The job fails loudly
  on dispatch (H-19). PyFR stack, frozen-optional.
- [ ] **A bare `dvc pull` can never succeed in this repository**: it also targets the DrivAerML
  dataset, which lives on the `aero-nfs` remote (ADR-011), not the default `aero-minio`. Every pull
  in CI is now targeted. Stage 23's content-addressed `dvc_input_hash` (O-07) must define inputs
  per case, across remotes.
- [ ] **`vv-smoke` floods the V&V experiment** (four runs per push; 18 in one day). The report no
  longer has a window, but the history listing and the MLflow UI do. Consider a separate smoke
  experiment or tag in Stage 24.

## Rigid-flapping optimization — pre-registration items carried from Stage 21

The stage was Stage 22 until ADR-051 moved it behind the foundation stages 22–26. Its prompt draft
is `docs/handoff-bundle/LATER-rigid-flapping-optimization.md`.

- [ ] **Per-evaluation crash tolerance in the optimizer loop** (external review addendum C,
  operator decision 2026-10-13). This must be fixed in the rigid-flapping stage's
  pre-registration ADR, then built in that stage's first PR.

  **What exists today.** Both drivers already skip a failed solve: `scripts/stage17_speedup_arm.py`
  and the `EvaluateBatch` path of `aero/optimize/accelerated.py`. A failed solve becomes `None`,
  still counts against the budget (pre-registered S8) and is recorded in `IterationRecord.results`.

  **What is missing:**
  1. a **bounded retry** for transient infrastructure failures (SSH or host faults, which the
     Executor's `transport_error` already distinguishes from a solver failure), with no retry for
     a deterministic divergence;
  2. the **failure signature persisted in the evidence**. Today it is only printed.

  **To pre-register:** whether a retry consumes budget. The S8 analogue is "every attempt is a
  spent eval", and it must be stated before any campaign runs.

  **Boundary, non-negotiable:** this is per-evaluation retry of independent, restartable airfoil
  or rigid-flapping solves only. It does **not** reopen coupled-FSI restart (ADR-045 A19 /
  ADR-046 S5).

## Post-v0.1.0 — deferred by operator decision

- [ ] **The JOSS submission** (deferred 2026-10-15). JOSS's pre-review screening requires evidence
  of research use, and aspirational future use is not enough. The paper's research-impact
  statement is "testing so far". **Resume when** a publication, an analysis using the platform, or
  an external adopter exists: rewrite the impact statement from it, then follow
  `docs/release/joss.md`. The prepared metadata is on branch `joss-submission` (closed PR #68).
  The release itself (v0.1.0, Zenodo DOI 10.5281/zenodo.23396402) is unaffected.

## Post-v0.1.0 — proposed ADRs awaiting implementation

- [ ] **ADR-050: a hosted, CPU-only, outsider-reproducible CFD number** (addendum B, operator
  decision 2026-10-13: ADR now, build later). The parts:
  - `blasius_flat_plate` on `ubuntu-24.04`;
  - a pinned Apptainer running the digest-pinned OpenFOAM OCI image;
  - a `LocalContainerExecutor`;
  - the off-cluster four-tuple semantics (an OCI digest; an empty-input DVC hash);
  - output as a `reproducibility-proof` crate;
  - a non-required `hosted-repro.yml`.

  It interacts with O-07 (a content-addressed `dvc_input_hash`).
