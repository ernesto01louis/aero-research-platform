---
# Required frontmatter — scripts/check_handoff_exists.sh parses these.
stage: 11
stage_name: "Stage 11 — Moving-Mesh + Unsteady Post-Processing Toolkit"
status: complete
date_started: 2026-07-01
date_completed: 2026-07-01
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-8
git_sha_start: "9eb65e543f9ba843e2a58e6ca2eebe6c9e550644"
git_sha_end: "21114c0519e89dfc9b64f25f0114c03cd621e377"
stage_tag: v0.0.11
next_stage: 12
next_stage_name: "Stage 12 — Verification & UQ Core"
---

# Stage 11 — Moving-Mesh + Unsteady Post-Processing Toolkit — (2026-07-01)

> `git_sha_end` is provisional (reconcile to the squash-merge SHA at the `v0.0.11` tag —
> the Stage-08/10 pattern). Work landed on branch `stage-11/moving-mesh-and-unsteady`.
> **`status: complete`** (the Stage-10 sense — GO gate met + debts honestly documented, no
> tolerance relaxed). The stage GO gate is **MET** (the oscillating-cylinder lock-in GO,
> St 0.63 %, a clean pass; the prompt's gate is AND/OR). The **plunging foil ran to completion**
> → a documented **CONCERN** (C_T≈0.96, converged + resolution-insensitive, but ~4.5× the
> *unverified* digitized reference 0.21 — evidence points at the reference, not the solver;
> verify/re-anchor in Stage 12). The **NACA-0012** transient-mean stays a documented **NO-GO**.
> Operator approved tagging `v0.0.11` on this basis (mirrors v0.0.10, tagged with a NO-GO +
> CONCERN). See §3/§7/§10.

## 0. Headline

The platform can now **move the mesh** and turn unsteady traces into the derived quantities
the flapping optimizer's objective is built from. The **primary GO is GREEN**: a forced
transversely-oscillating cylinder (Re=100, A/D=0.5, F=1.1) **locks in** — the wake response
Strouhal is **0.63 %** from the forcing frequency, from a **35-cycle converged limit cycle**,
and the pressure/viscous force split **closes exactly**. The morphing motion solver
(`dynamicMotionSolverFvMesh`, ADR-018) is validated on the real ESI v2412 SIF. The
`aero/postprocess/` toolkit (ADR-019) is typed, tested, and exposes the per-cycle-sample seam
Stage 12's `u95_statistical` consumes. The **plunging-foil ran to completion** (resolved,
cycle-converged, resolution-insensitive C_T≈0.96, net thrust) but is a **documented CONCERN**:
C_T is ~4.5× the *unverified* digitized reference 0.21 — evidence points at the reference value
(implausibly low; St=0.4 is the deflected-jet regime), not the solver. Not relaxed; verify the
reference / re-anchor at a lower St (Stage 12).

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Moving-mesh solve path (`dynamicMotionSolverFvMesh`; overset available) | ✅ | Morphing writers (`dynamicMeshDict`/`pointDisplacement`/`movingWallVelocity`/`pcorr`+`cellDisplacement`); `pimpleFoam` unchanged; **validated on the SIF** (2911 clean steps at A/D=0.5, no divergence/negative-volume). Overset libs confirmed present (fallback needs no rebuild). ADR-018. |
| 2 | `aero/postprocess/` unsteady toolkit | ✅ | 6 modules (frequency, phase_averaging, forces, efficiency, cycle_detection, _base), strict-pydantic, stdlib+numpy. 36 host unit tests. Force-closure is a schema invariant; `CycleSamples.per_cycle_mean` is the Stage-12 batch-means seam. ADR-019. |
| 3 | Moving-body V&V (oscillating cylinder + plunging airfoil) | ⚠️ | **Cylinder lock-in GO GREEN (St 0.63 %, 35-cycle converged, split closes; MLflow `816eae4b`).** Plunging-foil **ran to completion → documented CONCERN** (reference-limited): resolved solve is cycle-converged (19 cyc), resolution-insensitive (C_T 0.91→0.96), net thrust, split closes — but C_T≈0.96 is ~4.5× the **unverified** digitized ref 0.21 (implausibly low; St=0.4 is the deflected-jet regime). Verify reference / lower St; **not relaxed** (§3). |
| 4 | NACA-0012 transient-mean Cd rethink (optional) | ⚠️ | **Assessed → still-NO-GO on the blunt-TE remedy** (no relaxation). The transient path is now validated (makes the transient-mean route feasible), but a faithful y+<1 Re=6e6 URANS is multi-day and ADR-017's base-drag budget shows blunt-TE can't reach 3 % even converged; a wall-function shortcut confounds the 3 % test with the Stage-5 ~+20 % bias. Real fix = sharp-TE remesh / SU2 — Stage-13 follow-up (§3). |
| 5 | ADRs + handoff + Stage-12 prompt + tag v0.0.11 | ✅/⏳ | ADR-018 + ADR-019; this handoff; **Stage-12 prompt exists** (`docs/handoff-bundle/STAGE-12-vv-uq-core.md`). Tag decision pending (foil deferral — §10). |

## 2. Decisions made

- **Morphing primary, overset fallback (ADR-018).** `dynamicMotionSolverFvMesh` +
  `displacementLaplacian` + `inverseDistance` diffusivity (boundary-layer preserving). At
  A/D ≈ 0.2–0.5 and h0/c ≈ 0.175 morphing is *more accurate* than overset (no overlap
  dissipation) and reuses the existing grids + `pimpleFoam` — so "more intensive" (overset)
  would be worse, not better. `solidBodyMotionFvMesh` rejected (moving far field contaminates
  the external-flow force frame). Operator gave the motion-solver call to the agent.
- **postprocess is a standalone pure-function library, no `Solver` ABC change (ADR-019).**
  Results flow into `SolveResult.scalars`; the per-cycle samples are the Stage-12 seam.
- **Lock-in forced off-natural (F=1.1), not at F=1.0.** Makes the GO *discriminating*: an
  unlocked wake sheds near St_0=0.165 (9 % away), so the 3 % tolerance passes only on genuine
  synchronization.
- **Plunging-foil: honest 15 % band + trend/CFD-repro fallback** (operator decision). Laminar
  2-D at Re=1e4 (transition is Stage 13). Reference C_T digitized (provenance in
  `reference.md`; verify vs the primary figure — Stage-12 follow-up).
- **Reference data git-tracked** (tiny scalar tables, forward-regime tier convention) rather
  than DVC — a deliberate deviation (§3), so the V&V gate loads without a `dvc pull`.
- **Foil resolved-GO deferred, not forced with a coarse mesh.** A tractable wall-coarsened foil
  would under-resolve the LEV and confound the 15 % contract — the tolerance is a contract.

## 3. Deviations from the stage plan

- **Plunging-foil = documented CONCERN (reference-value-limited), not a clean GO.** The
  committed case (first_cell 2e-3, end_time 18) **ran to completion serially** (~a few h once
  `adjustTimeStep` grew the step past the transient; MPI parallelism is blocked — §6) and gives
  a **clean, cycle-converged (19 cycles), resolution-insensitive** result: **C_T ≈ 0.96**
  (coarse first_cell=5e-3 gave 0.91 — they agree, so the LEV is adequately captured), C_P≈6.0,
  η≈0.16, strouhal_heave=0.400 (exact), force split closes exactly, **net thrust** confirmed.
  **But C_T ≈ 0.96 is ~4.5× the digitized reference 0.21 — a MISS on the 15 % band.** The
  evidence points at the **reference value, not the solver**: (i) the solve is converged,
  resolution-insensitive, and self-consistent; (ii) a plunging foil at St=0.4, h0/c=0.175
  physically produces C_T ~ O(0.5–1.0) (thrust ∝ St²), so **0.21 is implausibly low** — and
  `reference.md` already flagged that value as an **unverified digitized estimate**; (iii) St=0.4
  is the rigid-foil **deflected-jet bifurcation** regime (asymmetric wake), a hard anchor.
  **Per the operator's fallback (never relax the tolerance):** documented as a **CONCERN** — the
  resolution is to **verify the HG C_T value + its normalization against the primary figure**
  and/or move the anchor to a **lower St (0.2–0.3, pre-bifurcation)**, a Stage-12 follow-up. A
  minor loader note: propulsive_metrics' integer-cycle C_T (0.96) vs the forceCoeffs tail-mean
  −Cd (1.28) differ ~30 % — consistent with the St=0.4 deflected/period-2 wake making the
  forcing-period segmentation approximate; worth a cross-check.
- **NACA transient-mean = assessed, not run** (§1 row 4). ADR-017's arithmetic already predicts
  NO-GO; the faithful run is multi-day; the shortcut is confounded. Documented, not relaxed.
- **Reference data git-tracked, not DVC** (the prompt said DVC). Justification: ~100-byte
  scalar tables; host↔cluster DVC-push friction; forward-regime precedent. A future *large*
  raw HG dataset would move to DVC.

## 4. Environment / dependency / schema changes

- New package `aero/postprocess/` (6 modules) — no new pyproject extras (numpy+pydantic base).
- `aero/adapters/openfoam/`: new `motion.py` (`MotionSpec` + dict writers) + `plunging_airfoil.py`
  (`PlungingAirfoilSpec` + writer); `CylinderSpec` gains `motion`; `solver.py` gains
  `_load_moving` + `_read_force_history` + a `PlungingAirfoilSpec` dispatch; `_foam_common.py`
  gains `transient_fvschemes` / `transient_fvsolution(cell_displacement)`.
- New `aero/vv/unsteady/` registry (2 cases) wired into `aero vv list/run`.
- `SolveResult.scalars` for a moving case: `strouhal`, `cycle_converged`, `n_converged_cycles`,
  `converged_from_cycle`, `mean_drift`, `amplitude_drift`, `forcing_period` (+ foil:
  `thrust_coefficient`, `power_coefficient`, `propulsive_efficiency`, `strouhal_heave`).
- New reference data `data/references/unsteady/{oscillating_cylinder_lockin,plunging_airfoil_hg2007}/`
  (git-tracked). New `scripts/stage11_moving_vv.py` (long-timeout runner driver).
- No DB/bucket/container-SHA changes.

## 5. CI/CD changes

- New cluster-bound (slow) V&V tests `tests/vv/test_unsteady_{oscillating_cylinder,plunging_airfoil}.py`
  (`@pytest.mark.slow/vv/stage_11`, `vv_cluster_ready` skip). Host tests under `tests/stage_11/`.
- No new required status checks.

## 6. Gotchas discovered

- **Moving-mesh `pimpleFoam` needs a `"pcorr.*"` solver + `correctPhi yes`** (the mesh-flux
  correction) AND a `cellDisplacement` solver — it aborts with a bare `fvSolution`. Fixed in
  `transient_fvsolution(cell_displacement=True)`.
- **The moving wall's `U` BC must be `movingWallVelocity`** (no-slip in the moving frame) — a
  plain `noSlip` silently biases the forces. Guarded by a host test.
- **apptainer does not bind `/mnt/aero` by default** — the platform binds the case to `/case`;
  a manual `apptainer exec` needs `--bind <case>:/case`.
- **`aero vv run` blocks on the executor's 30-min `long_timeout_s`** — too short for a moving
  solve; use `scripts/stage11_moving_vv.py` (multi-hour timeout) or run detached + collect.
- **Per-cycle mean of an oscillation wobbles** if computed as a plain sample-mean over a cycle
  window (boundary-sample inclusion). Fixed: integrate over exactly one period with
  interpolated endpoints (`segment_cycles`).
- **A shebang'd script must be `chmod +x`** or the `check-shebang-scripts-are-executable`
  pre-commit hook silently aborts the commit (bit me for 4 commits — watch the full output,
  not `tail`).
- **The plunging foil at Re=1e4 is far more expensive than estimated** — the fine wall +
  plunge-velocity Courant dominates; there is no accurate-and-fast shortcut.
- **MPI is blocked in the aero LXCs** (the real foil speedup path). `mpirun`/PMIx fails at
  `opal_ifinit: socket() errno=13` — the unprivileged-LXC network sandbox blocks `socket()`
  before any transport selection, so no `--mca` flag helps (the same limitation the SU2 build
  hit — CLAUDE.md). Parallel OpenFOAM (`decomposePar` + `mpirun pimpleFoam -parallel`) is
  therefore not runnable in-LXC; the foil is stuck on serial. Options to unblock: a privileged
  container / a Slurm or RunPod backend / an MPI-capable host. `decomposeParDict` writers must
  use the platform `header()` (a compact one-line FoamFile header fails to parse).

## 7. Open items for the next stage (and beyond)

- **Stage 12 (Verification & UQ Core):** prompt written. Batch-means `u95_statistical` over the
  Stage-11 converged-cycle samples (the cylinder already has 35 converged cycles); full U95;
  the `small-signal-gate` + `data_origin` CI gates; the ADR-015 constitution merge.
- **Plunging-foil CONCERN → resolve the reference (the actual blocker, not compute).** The
  resolved case RAN and converged (C_T≈0.96, resolution-insensitive); the 4.5× miss is almost
  certainly the **unverified digitized reference 0.21** (implausibly low vs the physics). Action:
  **verify the HG rigid-foil C_T value + its normalization convention against the primary figure**
  (AIAA J 45(5), the C_T-vs-St figure), and/or **re-anchor at a lower St (0.2–0.3)** below the
  deflected-jet bifurcation for a cleaner comparison. Then re-run/re-load
  (`OpenFOAMSolver().load(...)` on `/mnt/aero/runs/stage11-foil-parallel`, or the driver). Also
  cross-check the propulsive_metrics vs forceCoeffs C_T (~30 % gap at St=0.4 — the deflected/
  period-2 wake; §3). MLflow logging of the foil run is a quick follow-up (the run completed
  outside the runner). MPI-unblock (privileged/Slurm/RunPod) only matters if many foil runs are
  needed.
- **NACA-0012 transient-mean (real fix):** a **sharp-TE** TE-region remesh transient-mean (no
  base drag) or the SU2 cross-check — the blunt-TE remedy stays rejected.
- **Rigor:** clean-SHA reportable re-runs of the moving cases (GO used `--allow-dirty`); a
  combined space+time GCI per moving case (the `refined()` seams ship).

## 8. Pointers for next session

- **Read first:** this file + ADR-018/019 + the Stage-12 prompt + `git log origin/main..`.
- **Run first to verify:** `pytest tests/stage_11 tests/unit -q`, `mypy aero`,
  `ruff check aero tests scripts` (all green: 106 host tests). Cluster:
  `python scripts/stage11_moving_vv.py <case> --host aero-dev` (NOT `aero vv run` for a moving
  case — the 30-min timeout).
- **Do not re-read:** the cluster debug transcripts — conclusions are in §3/§6.

## 9. Artifacts produced

Commits on `stage-11/moving-mesh-and-unsteady` (see `git log`): `.aero-stage`; the
`aero/postprocess/` toolkit; the adapter refactor; `motion.py` + dict writers; the moving
cylinder + `_load_moving`; the plunging-airfoil case; `aero/vv/unsteady/` + CLI wiring;
reference data; cluster tests; the pcorr fix + driver + ADR-018/019 + Stage-12 prompt + foil
re-tune. New code: `aero/postprocess/*`, `aero/adapters/openfoam/{motion,plunging_airfoil}.py`,
`aero/vv/unsteady/*`, `scripts/stage11_moving_vv.py`, `data/references/unsteady/*`, host +
cluster tests, ADR-018/019, this handoff, the Stage-12 prompt. **MLflow (aero-mlflow):** the
oscillating-cylinder lock-in GO run `816eae4bdcc440acbbd486a44f673386` (St 0.63 %).

## 10. Confidence / risk note

High confidence: the moving-mesh capability (validated on the SIF) + the cylinder lock-in GO
(a clean 0.63 %, 35-cycle-converged, force-split-closing result, MLflow-logged) + the
`aero/postprocess/` toolkit (typed, 36 unit tests). The cylinder GO satisfies the stage's
formal (AND/OR) GO gate. The **plunging-foil ran and converged** (resolved + coarse agree on
C_T≈0.9–1.0, net thrust, split closes) — high confidence the *solve* is sound; the CONCERN is
that C_T is ~4.5× the **unverified digitized reference 0.21**, and the evidence (converged,
resolution-insensitive, physically-plausible O(0.5–1) at St=0.4) points at the reference being
wrong, not the solver — but I could not access the HG figure to confirm, so this is honestly a
CONCERN, not a claimed GO. Lower confidence: the exact HG C_T value + normalization convention;
the ~30 % propulsive-vs-forceCoeffs C_T gap at the St=0.4 deflected-jet bifurcation. The NACA
transient-mean stays a documented NO-GO. **Bus-factor / tag note:** the operator asked for both
GOs; the foil is a documented CONCERN (reference-limited), not a clean GO. Whether to tag
`v0.0.11` now (cylinder GO = stage gate; foil CONCERN + NACA NO-GO documented, the Stage-10
precedent) or hold until the reference is verified and the foil re-anchored is an operator
decision (§7).
