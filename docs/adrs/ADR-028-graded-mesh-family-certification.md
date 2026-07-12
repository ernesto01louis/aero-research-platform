# ADR-028 — Graded (fixed-mapping) mesh families for optimization-delta certification

- **Status:** accepted
- **Date:** 2026-07-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 16)
- **Stage:** 16 (Grid-Converged Certification of the Airfoil Optimum)
- **Pairs with:** ADR-020 (UQ core / GCI), ADR-023 (paired-difference delta), ADR-026 (the
  optimizer), ADR-029 (independent-RSS unsteady delta — the certification path this ADR's
  outcome hands off to)

## Context

Stage 15's optimizer found a real turbulent optimum (m≈0.0727, p≈0.2045; L/D 21.67→46.34,
+113% at Re=5e5, AoA 4°, k-ω SST wall-function) but certification failed: the matched-grid
delta was not grid-converged (delta 24.7→18.7→15.4 on 80²/47²/28², observed order −1.10,
GCI ≈ 103% of the delta) and the finer 136² grid diverged (SIGFPE). The Stage-15 handoff
attributed the divergence to `refined()` "steepening the near-wall grading into bad cells"
at fixed first-cell height, and Stage 16's prompt made "grade the first cell WITH the
refinement" the primary route.

## The corrected mechanism (evidence: `data/vv/stage16_divergence_diag.json`)

The handoff's one-liner is **directionally wrong**. With the wall-normal extent (100c) and
first cell (1e-3c) both pinned, the geometric cell-to-cell ratio r is a pure function of
`n_normal` — and it FLATTENS with refinement:

| n_normal | r (wall-normal) | end-to-end G | checkMesh max non-ortho / skewness |
|---|---|---|---|
| 28 (old) | 1.468 | 3.19e4 | 88.7 / 2.50 |
| 80 (base) | 1.125 | 1.11e4 | — (the working grid) |
| 136 (old) | 1.067 | 6.27e3 | 83.6 / 1.78 |
| 136 (graded) | 1.072 | 1.11e4 | 83.6 / 2.57 |

The steep, low-quality cells live on the **coarse** grids. The old-136² mesh is the
*gentlest* of its family and its quality equals the graded-136² mesh; every grid in both
families fails the same single checkMesh check (high non-orthogonality at the C-grid wake
cut — systematic, present on the working 80² base too). The old-136² optimum solve dies by
**SIGFPE inside GAMG's pressure solve after the forces blow up** (~iteration 400): the
divergence is **resolved unsteadiness** — the finer grid has less numerical dissipation, and
the loaded wake that limit-cycles mildly at 80² destabilizes the steady segregated iteration
at 136² — not bad cells.

The old family's real defect for GCI purposes is different: it is **not geometrically
self-similar**. The stretching mapping (r, hence G) drifts grid-to-grid, so the grids do not
nest and the observed-order GCI's premise (one mapping sampled at h, rh, r²h) does not hold.

## Decisions

1. **Fixed-mapping (pinned-G) refinement** (`aero/optimize/mesh_family.py`): hold each
   count-dependent direction's end-to-end expansion `G = expansion(length, n, first)` (the
   blockMesh `simpleGrading` value) constant across the family and scale the counts
   (`scaled_count`). First cells then scale ~1/ratio automatically ("grade the first cell
   WITH the refinement" — the prompt's route, now with the correct rationale: *nesting*, not
   cell quality); every grid samples one stretching mapping; y+ spans ~15 (136²) to ~72
   (28²), inside the all-y+ Spalding validity range, and the per-grid wall-function bias
   cancels in the per-grid matched delta.
2. **Front/wake first cells become `CaseSpec` fields** (`first_cell_front`,
   `first_cell_wake`, defaults 0.01 = the previously hardcoded constants) so the streamwise
   gradings scale with the family too. Defaults keep the baseline blockMeshDict
   byte-identical (pinned by tests).
3. **Wall-treatment branch guard:** `NUT_LOW_RE_FIRST_CELL_MAX` (1e-4c) is a named constant
   (`case_writer.py`); `graded_refined_spec` raises if a family would cross it — flipping
   the wall model mid-family would change the modelled physics between grids (FAIL-LOUD).
4. **`refined(ratio, *, graded=True)`** on both optimizer case classes. The default flip is
   deliberate (correctness by default); `graded=False` reproduces the Stage-15 count-only
   family for diagnostics/reproduction. Stage-15 artifacts pin their SHA.
5. **Hard-gated verdicts** (`aero/optimize/report.py::certification_gates`): GO requires
   significance AND all claim solves converged AND a monotone delta AND an observed order in
   [0.5, formal]. This closes a Stage-15 driver gap: `all_converged` was recorded but never
   gated the verdict.

## Outcome of the steady certification (the graded family run; `data/vv/stage16_grid_convergence.json`)

The graded family **cures the crash** (the old-136² SIGFPE becomes a bounded solve) and
reproduces Stage-15 exactly at the shared 80² grid (21.674 / 46.333). But the loaded optimum
at 136² enters a **violent two-iteration numerical limit cycle** (period ≈ 2 iterations —
a segregated-SIMPLE instability mode, not resolved vortex shedding at the sampling rate of
the residual history; cd crosses zero in 341/1000 tail iterations, swinging −0.032…+0.075
around a mean of 0.021). The tail-mean L/D (ratio of tail-mean forces, 46.61) is consistent
with the coarser grids, but no honest iterative-uncertainty number survives a
sign-crossing cd, and the delta series (coarsest→fine: 19.21 → 21.76 → 24.66 → 23.14) is
**non-monotone at the finest grid**. Verdict: **NO-GO on all four hard gates** — recorded,
not relaxed.

**Estimator artifact (recorded for the audit):** the drivers' pre-registered per-solve
convergence statistic (batch-means SEM of the *pointwise* cl/cd ratio, filtered to cd>0) is
statistically invalid when cd crosses zero — at 136² it *spuriously passed* the baseline
(SEM 0.087 measured on a filtered subseries whose mean, 6.26, is nothing like the reported
ratio-of-means 23.47) and failed the optimum (heavy-tailed 33.6). A well-defined per-batch
ratio-of-means statistic gives 23.474 ± 0.062 and 46.644 ± 0.556. The verdict was NOT
re-derived with the friendlier statistic — switching estimators after seeing a gate fail is
the bar-gaming this platform exists to refuse, and the finest-grid flow's two-cycle with
sign-crossing cd fails the deeper question (is the tail-mean of such an iteration a steady
solution at all?). The artifact means the steady campaign's fine-grid convergence flags are
unreliable in BOTH directions — reinforcing the NO-GO.

**Consequence:** steady `simpleFoam` cannot certify this optimum at the finest grid of a
legitimate family. Certification proceeds on the stage prompt's sanctioned fallback — the
time-accurate (URANS) path with a real, measured sampling term — specified in **ADR-029**.

## Rejected alternatives

- **Hold y+ fixed, refine only tangentially/outer blocks:** keeps the wall model identical
  per grid but abandons uniform refinement (only part of the domain refines) — order
  pollution, and the grid-legitimacy audit's easiest attack.
- **External pre-validated C-grid (NASA TMR):** the platform's own TMR NACA 0012 absolute
  validation is a NO-GO, so "inherited" convergence is not credible here; TMR grids target
  wall-resolved y+<1 at Re=6e6 — the regime Stage 15 established as intractable on this
  hardware (~67 min/solve, unstable for loaded designs).
- **Same-regime solver-setting tweaks to force convergence:** prohibited (three regimes
  exhausted in Stage 15; `.claude/rules/optimization-integrity.md`).
- **Re-deriving the verdict with the corrected iterative-uncertainty estimator:**
  rejected as bar-gaming (above); the estimator defect is documented instead, and the
  time-accurate path measures a physically meaningful sampling term.
