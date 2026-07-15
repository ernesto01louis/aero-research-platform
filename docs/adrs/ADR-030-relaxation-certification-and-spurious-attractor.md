# ADR-030 — Time-accurate relaxation certification; the spurious-attractor finding

- **Status:** accepted
- **Date:** 2026-07-15
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 16)
- **Stage:** 16 (Grid-Converged Certification of the Airfoil Optimum)
- **Pairs with:** ADR-028 (graded family; steady NO-GO), ADR-029 (independent delta U95 —
  schema landed and tested; the statistical path itself was ultimately not the claim route)

## Context — what the URANS campaigns actually found

The impulsive-start URANS campaign (maxCo 8, graded family) produced three findings
(`data/vv/stage16_urans_pathology.json`):

1. **Glacial settling.** From a uniform impulsive start on the 100c domain, force
   coefficients approach their steady values with e-folding times of tens of convective
   units (still trending at t*=100 on every baseline) — stationarity within a tractable run
   length is unreachable, and the NOBM reliability flags correctly refuse trend-dominated
   tails.
2. **A spurious attractor.** The loaded optimum at medium (80²) and fine (136²) resolution
   departs to a non-physical high-circulation state (medium: cl≈+3.9, cd≈−0.65, rock-steady
   over the committed t*=76–100 windows, onset ≈20 t* per the raw series on /mnt/aero/runs;
   fine: cl swinging 2.5–6.7, cd<0, impulsive-start evidence) while every recorded baseline
   run and the coarse optimum stay physical. At 80², initializing from the converged
   steady-RANS field does NOT prevent it at maxCo 8 — the solve departs within 2 t*.
3. **It is a large-timestep artifact** (`data/vv/stage16_courant_diag.json`). At maxCo 2
   and maxCo 4 (steady-RANS init, medium grid) the time-accurate solve STAYS on the physical
   steady solution and holds it through the full 20 t* diagnostics — Co 2: cd +0.0211 /
   cl +1.0040, Co 4: cd +0.0211 / cl +1.0032 in the final 4-t* window, flat from t*≈4 (cd
   dt-insensitive to 4 decimals, cl to ~1e-3). The full Co-4 relaxed campaign then held the
   physical solution on every grid including 231². The artifact threshold sits between Co 4
   and Co 8 for this family (Euler + PIMPLE, stretched C-grid).

Combined with ADR-028 (SIMPLE's pseudo-time iteration limit-cycles violently for the loaded
optimum at 136² though the mesh is good), the picture: **the physical flow is steady; the
pseudo-time SIMPLE iteration at fine resolution and large-Co Euler integration are both
numerically unstable for the loaded design.**

## Decision

1. **Certify via time-accurate relaxation** (`scripts/stage16_relaxed_cert.py`): initialize
   each graded-family case from its converged steady-RANS field (or, for rungs finer than
   any steady solve, by `mapFields -consistent` grid continuation from the finest relaxed
   solution), integrate pimpleFoam at maxCo 4 (below the measured artifact threshold,
   uniform across the family), and read the steady value from the flat tail (last-5-t*
   time-weighted mean). This is a stabilized steady solve — the sanctioned URANS path's
   degenerate case; physics, mesh family, hard gates, and k=2 untouched.
2. **Pre-registered per-solve gates** (committed before the campaigns): relaxation drift
   |ΔL/D| between the last two 5-t* windows ≤ 0.2%·|L/D|; steadiness (0.5-t* window spread ≤
   the same tolerance — a genuinely shedding flow FAILS and this composition refuses);
   physicality (window-mean cd > 0). Family gates + significance via `certification_gates` +
   `compose_result` (steady kind), u95_delta_iterative = RSS of the two finest-grid drifts.
3. **Refine-to-test:** when the {136,80,47} family measured a clean non-monotone delta
   (that 3-grid record is preserved at commit `9613124`), the family was EXTENDED one rung
   finer (231², six converged rows reused verbatim with provenance) — the opposite of the
   prohibited coarsen-until-it-passes.
4. The ADR-029 statistical path stays as landed, tested schema for genuinely unsteady
   quantities; this claim did not need it (the relaxed tails are flat).

## Outcome — honest NO-GO by a single pre-registered gate

Final family {231², 136², 80², 47²}, all eight solves converged inside the gates at
margins 1.6×–46× (tightest: the 231² optimum's steadiness at 1.6×)
(`data/vv/stage16_relaxed_convergence.json`, clean SHAs, per-row four-tuples; the known
single systematic checkMesh non-orthogonality flag at the wake cut persists on 231² as on
every family grid — ADR-028):

| grid | baseline L/D | optimum L/D | delta |
|---|---|---|---|
| 47² | 18.272 | 42.502 | 24.230 |
| 80² | 21.796 | 47.534 | 25.738 |
| 136² | 24.317 | 47.799 | 23.482 |
| 231² | 28.201 | 49.920 | **21.719** |

The {231,136,80} matched delta is **monotone** (25.738 → 23.482 → 21.719) and clears the
bar under the Fs=3, assumed-first-order (p=1) fallback GCI (delta 21.719 vs required
15.108) — but at the MEASURED sub-floor order 0.465 the same construction gives 2·U95 ≈
37.7, which the delta would not clear: significance is conditional on the fallback order.
The sole failing gate is the asymptotic-range floor: **observed order 0.465 vs the
pre-registered minimum 0.5** — committed in `certification_gates` before any campaign ran
and not adjusted after the fact. Verdict: **NO-GO**; the result ships as
`validation_tag="validated"` (`data/vv/stage16_relaxed_optimization.json`).

Interpretation, honestly stated: the delta is robustly positive on every grid, of stable
magnitude ~22–26 — but its discretization convergence is sub-first-order on this family,
and the ENDPOINT L/D series are themselves far from converged (observed orders −0.8
baseline / −3.9 optimum; per-quantity u95_numerical 59% of the baseline value and 18% of
the optimum in the shipped artifact). Only the matched delta partially cancels the
discretization error — consistent with the all-y+ wall-function bias drifting as y+ falls
25→9 across rungs — so a thesis-grade GCI cannot yet be claimed, on the delta or the
endpoints.
The next rung (393², ~2 weeks serial / ~10 days concurrent on aero-dev, scaling the
measured 231² wall times) and/or a wall-resolved family on bigger hardware are costed and
ledgered for a future stage.

## Rejected alternatives

- **Adjusting the order floor (0.5 → 0.46) after seeing 0.465** — textbook bar-gaming;
  refused (Hard Rule 12, optimization-integrity).
- **Longer impulsive-start URANS** — O(100+ t*) settling per solve; spurious attractor at
  maxCo 8 regardless.
- **Dropping the finest grid** — coarsen-until-it-passes, prohibited; we did the opposite.
- **393² now** — ~2 weeks of wall clock on current hardware for a single additional order
  estimate; deferred with cost recorded, not silently abandoned.
