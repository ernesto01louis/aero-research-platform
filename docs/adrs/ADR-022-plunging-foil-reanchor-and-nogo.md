# ADR-022 — Plunging-foil re-anchor: over-prediction resolved as a documented 2-D-vs-3-D NO-GO

- **Status:** accepted
- **Date:** 2026-07-06
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 13)
- **Stage:** 13
- **Supersedes:** none (resolves the Stage-11/12 plunging-foil CONCERN; extends ADR-020)

## Context and problem statement

Stage 12 left a documented CONCERN: the rigid plunging NACA-0012 (Heathcote-Gursul anchor) at
St=0.4 over-predicted thrust ~2-4x vs the primary-source-corrected experiment (cycle-mean
C_T ~= 1.26 vs the corrected reference ~0.30), and the batch-means estimator correctly refused it
(St=0.4 is the period-2 deflected-jet regime, not cleanly cycle-converged). Stage 13 must
**resolve** this: re-run with transition (`kOmegaSSTLM`) and/or **re-anchor at a pre-bifurcation
St 0.2-0.3** (where the experiment IS measured, C_T ~= 0.20 / 0.22), compose a full-U95
`ReportableResult`, and either close the gap to within the 15% contract or **root-cause + document
the residual — never relaxing the tolerance** (Hard Rule 15; the stage prompt).

## Decision drivers

- A tolerance is a contract — the case's 15% thrust tolerance (Stage 11) is **never relaxed**.
- The re-anchor must be **defensible, not selection-biased**: use the experiment's measured St
  (0.2, 0.3), not an St cherry-picked to make the solver agree (`optimization-integrity.md`).
- The **transition MODEL** must be trustworthy for Stage 14 (rigid flapping) — verified separately
  on T3A (ADR-021); the plunging foil is a hard *validation* case, not a Stage-14 dependency.
- Serial-only compute (MPI blocked); the paired laminar-vs-transition comparison must be tractable.

## Considered options

1. **Re-anchor at St 0.2 + 0.3, laminar AND `kOmegaSSTLM`, on a matched mesh; report whichever
   clears, else document the root-caused residual.**
2. **Chase an St where the 2-D solve happens to match** (near the C_T(St) crossover) to force a
   pass.
3. **Relax the 15% tolerance to the ~15-40% model-form band** the prompt mentions.

## Decision outcome

Chose **Option 1**. The four re-anchored runs (each a dead-steady converged limit cycle,
`scripts/stage13_reportable.py`, C_T = -mean(Cd) over the converged tail; batch-means
`u95_statistical` is sign-symmetric so it is computed on the Cd series):

| St | laminar C_T | +`kOmegaSSTLM` C_T | corrected HG ref | best anchor error |
|---|---|---|---|---|
| 0.2 | 0.130 | 0.144 | 0.20 | **28% under** |
| 0.3 | 0.348 | 0.363 | 0.22 | **58% over** |
| 0.4 (Stage-12) | ~1.26 | — | 0.30 | ~320% over |

**Finding — the 2-D solve's C_T(St) slope is far too steep.** The experiment is nearly flat
(0.20 -> 0.22 -> 0.30 over St 0.2 -> 0.4); the 2-D solve rises steeply (0.13 -> 0.35 -> 1.26),
**crossing the experiment near St ~= 0.23** and **missing both measured points**. So the Stage-12
"over-prediction" was not a uniform bias — it is an St-dependent slope error that under-predicts at
low St and over-predicts at high St. **No re-anchored rung clears the 15% contract.**

**Transition barely moves it.** At Re_c = 1e4 with a clean free stream (Tu = 1% -> Langtry-Menter
Re_theta ~= 584), `kOmegaSSTLM` predicts near-laminar attached flow, so transition changes C_T by
only ~5-11% (St=0.2: 0.130 -> 0.144, *toward* the reference; St=0.3: 0.348 -> 0.363, slightly
*away*). It does not close the gap at either point — a legitimate finding, not a tuning failure.

**Determination: the plunging-foil unsteady rung is a documented NO-GO** (the stage prompt's
explicit provision: "if the unsteady-airfoil case cannot be brought within band even with
transition + a defensible re-anchor, STOP and document ... never relax the tolerance"). **Root
cause:** the 2-D-vs-3-D model-form gap (a 2-D foil misses the spanwise/finite-AR flow that flattens
the real thrust curve) compounded by the teardrop-vs-NACA-0012 geometry substitution. The results
ship as `validated` (a full RSS U95 envelope, failing anchor -> not thesis-grade; the composer
downgrades automatically).

**What the re-anchor DID achieve** (deliverable 2, "resolve the over-prediction"): (i) a **massive
improvement** over Stage-12 — anchor error 320% -> 28-58%; (ii) the **trend is validated** — C_T is
monotone in St with a net-thrust threshold near St ~ 0.17 (the thesis-fallback the Stage-11 case
docstring named); (iii) the over-prediction is **root-caused + characterized** (St-dependent slope
error), turning a vague CONCERN into a quantified model-form limitation.

**Crucially, this does NOT block Stage 14.** The flapping flagship builds on the **transition
model** (verified on T3A, ADR-021) applied to a **flapping wing** validated against Dickinson/Wang
— not on the plunging foil. The plunging-foil NO-GO is a bounded statement about a 2-D substitute
geometry, not about the transitional path.

### Mesh / numerics decisions (recorded)

- Laminar and `kOmegaSSTLM` share the **Stage-11-proven 2e-3 moving mesh** (n=90/70, maxCo=1.0) —
  a clean paired comparison (only the model differs). A finer 5e-4 wall-resolved mesh both diverged
  the moving-mesh startup (SIGFPE in the GAMG pressure solve at the impulsive heave) AND drove
  dt ~ 1e-4 (serially infeasible ~60 h). The shared mesh costs the transition probe wall resolution
  (y+ ~ 1.4 vs textbook y+<1, tolerated by the `kOmegaSSTLM` wall functions) — a qualitative probe,
  not a wall-resolved transition study.
- **Foil GCI cut** (the Stage-12 / ADR-020 precedent): the foil is a documented NO-GO regardless of
  discretization, so a space+time GCI adds no value (`u95_numerical = 0` in the composed result).
  The batch-means `u95_statistical` + reference `u95_input` (~15%, the in-range measured-point
  scatter — far smaller than the ~40% at the out-of-range St=0.4) still compose a real RSS envelope.

## Pros and cons of considered options

### Option 1 — re-anchor + honest NO-GO (chosen)
- Good: honest; tolerance intact; root-caused + characterized; massive improvement over Stage-12;
  the trend validated; does not block Stage 14 (transition model verified separately).
- Bad: the unsteady-airfoil rung is a NO-GO (the DoD's "clears its anchor" is not met by the foil).

### Option 2 — chase the crossover St
- Good: would produce a passing number.
- Bad: selection bias / metric misuse (Luo et al. 2509.08713) — "moving the goalposts to where the
  solver works." Rejected on integrity grounds.

### Option 3 — relax the tolerance to 15-40%
- Good: the foil would "pass."
- Bad: relaxing a contract tolerance is forbidden (Hard Rule 15; ADR-005). Rejected outright.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-13-transition-and-unsteady-airfoil.md`
- Related ADR: ADR-021 (transition-model pin + T3A), ADR-020 (UQ core / batch-means / foil-GCI cut),
  ADR-017 (forward-regime + transient seed)
- Related handoff: `docs/handoffs/STAGE-13-transition-and-unsteady-airfoil-DONE-2026-07-06.md`;
  `docs/handoffs/STAGE-12-vv-uq-core-DONE-2026-07-05.md` (the CONCERN this resolves)
- Reference: `data/references/unsteady/plunging_airfoil_hg2007/reference.md`
- External: Heathcote & Gursul (2007) AIAA J 45(5):1066; Heathcote PhD thesis (Bath); Camacho et al.
  (2020) Energies 13(8):1861 (2-D RANS reproduction, ~0.56-0.67 at St=0.4 — between our 2-D and the
  experiment, corroborating the fidelity-ordering).
