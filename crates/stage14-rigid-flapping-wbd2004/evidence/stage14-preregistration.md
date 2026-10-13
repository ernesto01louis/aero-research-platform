# Stage 14 — Rigid Flapping-Wing Validation: pre-registered acceptance criteria

> **Purpose (the F2 lesson).** The 2026-07 external review (finding F2) recommended
> **pre-registering** a validation case's acceptance criterion *before* running it, so the
> outcome cannot be rationalised after the fact. This document fixes the Stage-14 gated quantity,
> its acceptance band, and the diagnostics — committed **before any campaign solve**. A miss is
> **investigated and documented as a NO-GO; the band is never relaxed to pass** (Hard Rule 15,
> `optimization-integrity.md`).
>
> **Status:** RATIFIED — the operator signed off the 25 % band on 2026-07-09 (before any campaign
> run). It is now immutable for the stage; a miss is a documented NO-GO, never a relaxation. The
> metric tolerance is encoded in `aero/vv/flapping/wbd2004.py` (`_MEAN_CL_TOLERANCE`); this document
> records its derivation.

## Case

`flapping_wing_wbd2004` — a rigid 2-D thin-elliptic wing in prescribed flapping hover
(`FlappingWingSpec` + `FlappingMotionSpec`), reproducing Wang, Birch & Dickinson (2004)'s 2-D
computation. Baseline kinematics (WBD Eqs 10–11): `alpha0 = 90°`, `beta = 45°`, `A0/c = 2.8`,
`Re = 75`, laminar, quiescent domain. Three rotation timings: symmetrical (`phi = 0`), advanced
(`+45°`), delayed (`−45°`). Coefficients use the WBD normalisation (peak quasi-steady force;
`aero/postprocess/flapping_forces.py`), reproducing the paper's reported numbers 1:1.

## Gated quantity (GO/NO-GO)

**The symmetrical-rotation stroke-averaged mean lift coefficient `mean_lift_coefficient`**,
composed into a full-U95 `ReportableResult` and compared against the **WBD experiment** value.

- Reference (anchor): `mean_cl_experiment = 0.86` (WBD 3-D robotic-wing, symmetrical rotation;
  text-sourced, `data/references/flapping/wbd2004_2d_ellipse/`).
- **Acceptance band: `|mean_CL − 0.86| / 0.86 ≤ 0.25` (25 % relative).**
- Full U95 required for thesis-grade: `u95_numerical` (space+time GCI, `scripts/stage14_gci.py`) +
  `u95_statistical` (batch-means over ≥16 converged cycles, `reliable`) + `u95_input` (≈5 %,
  `estimated`). Clean (non-`-dirty`) SHA required (review P1b).

### Why symmetrical, and why 25 %

- **Why symmetrical is the anchor, not advanced/delayed.** WBD found that 2-D reproduces 3-D well
  for **advanced and symmetrical lift and for all drag**, but the **delayed** timing is a
  documented 2-D failure (their own 2-D under-predicts the delayed mean lift ~2× with a phase
  shift). Gating on delayed would invite dishonest relaxation; it is a diagnostic (below).
- **Why 25 %.** The band is derived *before our CFD exists*, from the measured 2-D-vs-experiment
  gap plus honest model-form headroom:
  - WBD's **own 2-D computation** reproduced the symmetrical experiment to **−5 %** (0.82 vs 0.86).
  - Our solve differs from theirs in code, mesh (coarser, serial), and the (paper-unspecified)
    ellipse thickness ratio — call this ≤ ~15 % additional model-form/discretisation headroom.
  - Reference/reporting precision `u95_input ≈ 5 %`.
  - Summed conservatively → **25 %**. This passes a faithful 2-D solve (WBD's own reached 5 %) yet
    is tight enough to catch a broken kinematics/normalisation/mesh (which would miss by ≫25 %).

## Diagnostics (reported, NEVER gated)

- **Advanced** (`+45°`) mean C_L vs experiment 0.93, and **delayed** (`−45°`) vs 0.38 — reported;
  delayed is a documented 2-D limitation, not a pass/fail.
- The **advanced > symmetrical > delayed** mean-lift ordering (the Dickinson 1999 rotation-timing
  signature) — strong corroborating evidence at zero extra machinery.
- **Mean drag** C_D (symmetrical exp 1.34 / WBD-2D 1.44) and the **mean-drag ≈ 0** net-horizontal
  symmetry check (the hover analogue of the ADR-018 zero-amplitude regression).
- **Phase-resolved** lift/drag traces vs WBD Figs 2–4 (figure-locked; a qualitative overlay, not a
  gate) and the LEV vorticity/Q phase snapshots.

## NO-GO handling

If the symmetrical mean C_L misses the 25 % band, **stop and document**. Investigate — in order —
the mesh-motion tier (R0 `checkMesh`), the domain size, the ellipse thickness ratio, the pivot
location, and the kinematics fidelity. Do **not** relax the band, and do **not** substitute a
different gated quantity to obtain a pass. A documented NO-GO (as with the Stage-13 plunging foil)
is the honest outcome; the Stage-15 optimizer must not build on an untrusted forward model.

## Provenance ordering

This document + the reference CSV + the case tolerance are committed **before** any campaign run,
so every campaign `git_sha` is a descendant of the pre-registration commit (a machine-checkable
"declared before observed" ordering). Campaign runs use `allow_dirty=False` (a `-dirty` SHA cannot
be thesis-grade — review P1b).
