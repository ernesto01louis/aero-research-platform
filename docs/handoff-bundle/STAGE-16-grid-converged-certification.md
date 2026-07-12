# STAGE 16 — Grid-Converged Certification of the Airfoil Optimum

> Stage 15 built the CFD-in-the-loop shape optimizer and proved it finds real, large L/D improvements
> (+113% turbulent), but could **not** certify one to thesis-grade: a *loaded* airfoil resists a
> grid-converged steady CFD solution on tractable meshes, so the matched-delta's GCI balloons and every
> shortcut was (correctly) rejected by adversarial verification. **Stage 16's single job is to CERTIFY
> the improvement the optimizer already finds** — to reach the asymptotic grid-convergence range for the
> loaded optimum so a matched-delta clears `2·U95` honestly. The optimizer is done; this is a *V&V /
> meshing* stage, not an optimizer stage.

## BEFORE YOU START — READ

1. `docs/handoffs/STAGE-15-*-DONE-*.md` — **esp. §3 (the +47%/+17% retractions) and §6 (why every
   regime failed grid convergence).** Do NOT re-derive; do NOT re-attempt a same-regime config tweak.
2. `CLAUDE.md` Hard Rule 12 (IMPROVEMENT-EXCEEDS-UNCERTAINTY), Hard Rule 14, `.claude/rules/
   optimization-integrity.md`, `docs/vv/output-validity-bar.md`.
3. ADR-026 (the optimizer), ADR-005 (the C-grid), the turbulent path: `aero/optimize/turbulent_airfoil.py`,
   `aero/adapters/openfoam/case_writer.py` (`nut` wall BC + solver overrides), `solver.load_time_averaged`.

## The one hard problem

The optimizer's turbulent optimum (m≈0.073, p≈0.20, L/D 21.7→46.3) is real at every grid, but:
- coarse grids (28²/47²) are wildly under-resolved (delta 24.7→18.7→15.4 → huge GCI);
- the base 80² grid is the finest that solves — **finer grids (136²) diverge** because `refined()`
  scales cell counts while holding `first_cell_height` fixed, steepening the near-wall grading into
  bad cells.

So the asymptotic range is out of reach *with the current mesh-refinement strategy*. Fix that.

## Deliverables (pick the route with the best convergence evidence; document why)

1. **A grid family that reaches the asymptotic range for the loaded optimum.** The most promising
   route: make `refined()` grade the first cell WITH the refinement (keep y+ / expansion-ratio sane as
   cells are added) so finer turbulent grids converge instead of diverging — then a proper 3+ grid GCI
   on the matched-delta has a *monotone, bounded* observed order. Alternatives (document the choice):
   a **pre-validated external NACA C-grid** (NASA TMR / published) so grid-convergence is inherited; or
   the **URANS / time-averaged** path with real `u95_statistical` (the flapping paired-difference
   machinery) if the loaded wake is genuinely unsteady rather than a numerical limit-cycle.
2. **A CFD-verified, grid-converged, thesis-grade improvement** OR an honest documented NO-GO. Run the
   optimizer's optimum through the fixed grid family; compose via `MatchedGridDeltaTriplet` (grid GCI +
   iterative U95). GO iff the grid-converged `delta > 2·U95` with a monotone/bounded observed order and
   the finest grid INCLUDED (no coarsen-until-it-passes — the Stage-15 adversarial panel will be re-run).
3. **Re-run the adversarial-verification panel** (grid-legitimacy / UQ-honesty / physics) on the result
   BEFORE reporting GO. A result that cannot survive it is not thesis-grade — full stop.
4. ADR (the certified mesh strategy) + handoff + Stage-17 prompt + tag `v0.0.16`.

## GO / NO-GO

**GO** = a matched-delta that is grid-converged (monotone/bounded observed order, finest grid included,
all solves converged) and clears `2·U95`, and survives the adversarial panel. **NO-GO** = if the loaded
airfoil cannot be grid-converged even with a proper graded-refinement family, document it honestly and
fall back to the URANS/time-averaged path or an external validated mesh — never relax the bar, never
drop the finest grid to pass.

## Infra + conventions

Serial OpenFOAM (MPI blocked), 16-core aero-dev, detached driver. The tractable turbulent config
(Re=5×10⁵, wall-function, ~2-3 min/solve) is the working substrate — extend its meshing, don't replace
the optimizer. Clean-tree provenance for the reported run. Conventional commits `<type>(stage-16)`;
branch + PR; the four-layer memory/handoff discipline.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-16-*-DONE-*.md` (frontmatter + 10 sections). Emphasize the mesh strategy that
finally reached grid convergence (or the honest reason it couldn't), the certified delta + its full U95
breakdown, and the adversarial-panel verdict. Confirm the Stage-17 prompt exists (surrogate-accelerated
optimization on the now-certified own-data corpus — the deferred
`docs/handoff-bundle/STAGE-16-surrogate-accelerated-optimization.md` slides to Stage-17). Tag `v0.0.16`.
