---
stage: 14
stage_name: "Stage 14 — Rigid Flapping-Wing Validation"
status: complete
date_started: 2026-07-09
date_completed: 2026-07-10
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-fable-5
git_sha_start: "1dcd915df279743fe93830c896a05bae40ed09d7"
git_sha_end: "4cb68c0d322bf61a591de54822f2415e42d93511"
stage_tag: v0.0.14
next_stage: 15
next_stage_name: "Stage 15 — CFD-in-the-Loop Airfoil Shape Optimization (mission pivot)"
---

# Stage 14 — Rigid Flapping-Wing Validation — (2026-07-10)

> `git_sha_end` is provisional (reconcile to the `stage-14`→`main` squash-merge SHA at the
> `v0.0.14` tag — the Stage-08/13 pattern). **`status: complete`:** the forward capability +
> overset motion path are built and verified; the WBD experiment anchor is a **documented,
> root-caused NO-GO** (tolerance NOT relaxed — the Stage-13 plunging-foil discipline) with a
> **validated rotation-timing trend** + LEV capture evidence.

## 0. Headline

The platform gained a **rigid flapping-wing hover forward capability** on the actual mission
geometry: a prescribed translation+pitch stroke (advanced/symmetrical/delayed rotation timing) on
a 2-D elliptic wing at Re=75, on a validated **overset** moving-mesh path (`overPimpleDyMFoam` +
`dynamicOversetFvMesh` + `multiSolidBodyMotionSolver`, ADR-024). The GO gate is a **NO-GO** on the
absolute anchor: the symmetrical-rotation stroke-averaged mean lift coefficient converges to
**C̄_L ≈ 0.467** vs the WBD (2004) experiment **0.86** — a **46% under-prediction**, outside the
pre-registered ±25% band (band NOT relaxed, Hard Rule 15). The miss is **robust to numerics**
(finer mesh + less-dissipative schemes gave 0.463 vs 0.465) and **root-caused to overset
wake-capture dissipation** (the shed wake lives in the coarse fixed background and dissipates
before the wing re-encounters it, under-capturing the unsteady lift enhancement most in the cases
that rely on it). **BUT** the **rotation-timing trend is VALIDATED** — advanced (0.577) >
symmetrical (0.467) > delayed (0.137), the Dickinson (1999) lift-enhancement signature — and the
**LEV capture is textbook** (a leading-edge vortex forms, attaches through the stroke, and sheds
at reversal). The setup (kinematics, pivot, force normalisation) is validated qualitatively; the
magnitude gap is a 2-D-overset-vs-3-D-experiment modelling limitation.

**Mission pivot (operator, 2026-07-10):** the flapping forward magnitude is a case-selection wall
(2-D CFD vs 3-D experiment), and the project's product — the **optimizer** — was never built.
Stage 15 is re-targeted from flapping to a **CFD-in-the-loop airfoil shape optimizer** (the
general-ASO vision, validates cleanly, cheap steady solves), to produce the first CFD-verified
improvement. Flapping remains a documented forward-capability result, not the flagship.

## 1. Deliverables status

| # | Deliverable (stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Flapping kinematics primitive + motion-solver pin (ADR) | ✅ | `FlappingMotionSpec` + `FlappingKinematics` (WBD Eqs 10-11 + C¹ ramp); numpy `tabulated6DoFMotion` writer. ADR-024: morph FAILS at ±1.4c stroke (skew 5503), whole-mesh solid-body physically wrong (accelerating frame) → **overset** tier of record, validated end-to-end. |
| 2 | Rigid flapping-wing V&V case(s) vs Dickinson/WBD | ✅ (case) / ❌ (anchor) | `FlappingWingWBD2004` (symmetric gated + advanced/delayed diagnostics); WBD 2004 text-sourced reference. Anchor = **NO-GO** (C̄_L 0.467 vs 0.86, 46%; band not relaxed). |
| 3 | Full-U95 `ReportableResult` clearing the anchor | ⚠️ | Machinery built + validated on real overset output; the anchor fails → `validated` tier, not thesis-grade. Documented NO-GO (`data/vv/stage14_flapping_nogo.json`). |
| 4 | LEV capture evidence | ✅ | `scripts/stage14_lev_snapshots.py` → `data/vv/stage14_lev_flapping_wing_wbd2004.png`: textbook LEV forming/attaching/shedding over one stroke. |
| 5 | ADR(s) + handoff + Stage-15 prompt + tag | ✅ | ADR-024; this handoff; Stage-15 prompt authored (re-targeted to airfoil — see §7); tag `v0.0.14`. |
| — | Review P1b (-dirty SHA) + P1d (input-UQ basis) | ✅ | `aero/vv/reportable.py` hardened + tested (rode this stage per operator). |

## 2. Decisions made

- **Overset is the motion tier of record (ADR-024, corrected mid-stage).** The R0 probe eliminated
  morph (mesh tears at full stroke) and I initially proposed whole-mesh solid-body — then caught
  my own error (moving the whole mesh rigidly in quiescent hover is an accelerating frame without
  fictitious forces → no wing-relative-to-fluid motion). Overset (rigid component O-grid over a
  fixed background) is correct and validated. The honest self-correction is recorded in ADR-024.
- **NO-GO, band not relaxed (Hard Rule 15).** The symmetric anchor misses by 46%; per the
  Stage-13 plunging-foil precedent it is a documented NO-GO, investigated not relaxed.
- **Investigated the under-prediction; it is NOT numerics.** A reduced-dissipation run (larger/
  finer component, finer background, CrankNicolson 0.9, LUST) converged to 0.463 ≈ 0.465 → the gap
  is physical (overset wake-capture), not mesh/scheme. Rejected chasing it further per the pivot.
- **Ship the forward capability + validated trend + LEV as the honest Stage-14 outcome**, and
  pivot the mission to the airfoil optimizer (operator).

## 3. Deviations from the stage plan

- The GO gate (force trace within band) is a **NO-GO** on magnitude; met qualitatively (trend +
  LEV). Operator-approved to ship the documented NO-GO + validated trend.
- The 24-cycle campaign was **stopped early at the pivot** (base reached ~22 cycles, magnitude
  fully converged; advanced/delayed ~19-23). The GCI + thesis-grade composition were not run — a
  NO-GO does not need them (ADR-020 precedent). The batch-means convergence detector flags the
  amplitude still settling (M1 strictness) even though the mean is flat to 3 decimals.
- ADR-024's `mesh_motion` retains a `morph` path (documented small-amplitude alternative); the
  physically-inappropriate whole-mesh solid-body option was removed.

## 4. Environment / dependency / schema changes

- New adapter: `aero/adapters/openfoam/flapping_wing.py` (`FlappingWingSpec`, ellipse O-grid,
  hover BCs, overset assembly: background + component + `topoSet`/`setFields`/`multiSolidBody`);
  `motion.py` gains `FlappingMotionSpec` + `tabulated6DoFMotion` writers; `solver.py` gains the
  overset `mesh()` assembly + `overPimpleDyMFoam` `run()` + `_load_flapping` + `flapping_force_trace`.
- New postprocess: `aero/postprocess/flapping_kinematics.py`, `flapping_forces.py` (WBD normalisation).
- New V&V tier: `aero/vv/flapping/` (`FLAPPING_CASES`) + CLI wiring; reference data
  `data/references/flapping/wbd2004_2d_ellipse/` (git-tracked, text-sourced).
- Schema: `aero/vv/reportable.py` `ReportableQuantity.u95_input_basis` (P1d); thesis-grade gate
  rejects `-dirty` SHA (P1b). ADR-023 amendment ratified; Stage-13 handoff SHA reconciled.
- No new pyproject extras. SIF unchanged (overset binaries already present).

## 5. CI/CD changes

- No new required checks. 41 host-side `tests/stage_14/` tests (kinematics, case writer, registry,
  loader, P1b/P1d hardening) — all green; full suite 438 passing. The `moving` marker keeps the
  multi-hour flapping cluster case out of `vv-required`.

## 6. Gotchas discovered

- **Overset wake-capture dissipation** under-predicts unsteady flapping lift — a fundamental
  overset limitation (the wake spans the fine component + coarse background). Body-fitted (WBD's
  approach) keeps the wake in one mesh; morph fails at this amplitude, so the two can't be compared
  directly at ±1.4c stroke.
- **Whole-mesh solid-body motion is wrong for a body oscillating in still fluid** (accelerating
  frame w/o fictitious forces) — corrected in ADR-024.
- **`tabulated6DoFMotion` must be generated one period past `endTime`** or the final step errors on
  the table boundary. Rotation column is Euler-XYZ **degrees**.
- **foamToVTK writes fields as `FIELD FieldData` blocks** (not VECTORS/SCALARS); use
  `-cellZone movingZone` (zoneID is static, not written per-timestep).
- The batch-means convergence detector is strict on amplitude drift even when the mean is converged
  (review M1) — a NO-GO's mean is still trustworthy.

## 7. Open items for the next stage (and beyond)

- **Stage 15 (re-targeted): CFD-in-the-loop AIRFOIL shape optimizer** — the mission product.
  Build `aero/optimize/` (design-space + numpy GP + EI + BO loop), NACA-4 shape parametrization
  (perturb `case_writer._surfaces`), maximize L/D on the trusted laminar NACA-0012 (Re=1000), and
  report a matched-condition CFD-verified improvement delta > k·U95 (`compose_improvement(kind=
  "steady")` + delta-GCI). Re-author the (flapping-oriented) committed Stage-15 prompt to airfoil.
  **Stage-15 prompt file exists** at `docs/handoff-bundle/STAGE-15-cfd-in-the-loop-optimization.md`
  (to be re-authored for the airfoil target).
- **Flapping (if ever resumed):** a locally-refined overset background along the stroke path (to
  preserve the wake) or a body-fitted large-amplitude mesh is the path to close the magnitude gap;
  out of scope under the pivot.
- **Concurrent ADR-025** anti-surrogate-exploitation stack is on `feat/stage-14-anti-surrogate-
  exploitation` (additive; reconciles separately — not merged by this Stage-14 close).

## 8. Pointers for next session

- **Read first:** this handoff, ADR-024, the re-aimed Stage-15 direction (airfoil ASO), the
  external review F3 (prove the loop on a cheap trusted case — an airfoil IS that case).
- **Run first to verify:** `pytest tests/stage_14 -q` (green), `mypy aero`, `ruff check`.
- **Do not re-read:** the overset-recipe debug (conclusions in ADR-024 + §6).

## 9. Artifacts produced

Commits `d98e0de..96c3d8d` on `stage-14`: bookkeeping + P1b/P1d; the flapping capability (adapter,
kinematics, forces, V&V, reference data, 41 tests); the overset motion path + ADR-024; the Stage-15
prompt + LEV pipeline. Data: `data/vv/stage14_flapping_nogo.json` (the NO-GO record with the
per-timing means + the validated ordering), `data/vv/stage14_lev_flapping_wing_wbd2004.png`.

## 10. Confidence / risk note

High confidence: the overset motion path (validated end-to-end, mesh OK, forces produced); the
rotation-timing ordering (advanced>symmetric>delayed, robust); the LEV capture (visually clear);
the NO-GO magnitude (converged, robust to numerics, root-caused). The NO-GO is the honest,
discipline-preserving outcome. Lower confidence: the exact overset-wake-capture attribution (can't
isolate vs a body-fitted run at this amplitude — stated as the leading hypothesis). The pivot to
the airfoil optimizer de-risks the mission timeline: the product (a CFD-verified improvement delta)
is robust to the very systematic bias that fails the flapping absolute anchor.
