# ERCOFTAC T3A transitional flat plate — skin-friction reference data

**Case:** `t3a_flat_plate_transition` — a zero-pressure-gradient flat plate under ~3%
free-stream turbulence intensity (FSTI), U_inf = 5.4 m/s, nu = 1.5e-5 m^2/s. The boundary
layer undergoes **bypass transition** from laminar to turbulent at Re_x ~ 1.4e5. The measured
quantity is the local skin-friction coefficient Cf(x): it falls along the laminar branch,
reaches a **minimum at transition onset (x ~= 0.395 m from the leading edge)**, then rises to
the turbulent branch.

**Tier:** forward-regime credibility / transition machinery (Stage-13 — the canonical
verification case for the Langtry-Menter gamma-Re_theta `kOmegaSSTLM` transition model added
this stage). It is the transition-onset half of the Stage-13 GO gate.

## Source

ERCOFTAC T3A test case (3% FSTI). Skin-friction data as compiled/distributed with the
**OpenFOAM-ESI v2412 tutorial** `incompressible/simpleFoam/T3A/validation/exptData/T3A.dat`
(`x [mm]  c_f  Tu [%]`), which cites:

- Savill, A. M. (1993), "Some recent progress in the turbulence modelling of by-pass
  transition," in *Near-Wall Turbulent Flows*, 829–848.
- Savill, A. M. (1996), "One-point closures applied to transition," in *Turbulence and
  Transition Modelling*, Springer, 233–268.

The underlying experiment is the ERCOFTAC/Rolls-Royce T3 series (Roach & Brierley).

## `cf.csv` — skin-friction vs streamwise station

Columns: `x` (metres **from the plate leading edge**; the tutorial `x [mm]` / 1000), `cf`
(local skin-friction coefficient), `tu_pct` (local free-stream turbulence intensity, %,
retained for provenance — it decays downstream). 16 points, x = 0.045 .. 1.495 m, copied
verbatim from `T3A.dat` (no digitization — the tutorial ships tabulated values).

The **plate leading edge is at x = 0 here**; the ported mesh places it at physical x = 0.04 m
(there is an upstream contoured-nose contraction), so the case's `evaluate()` maps the sampled
physical x to x-from-LE by subtracting 0.04 m before comparing.

## Metrics (contracts — never relaxed)

1. **`transition_onset_rex`** (primary GO metric): Re_x = U_inf · x_min / nu at the Cf
   **minimum**, a scale-invariant, reproducible onset proxy. Reference: the Cf minimum is at
   x = 0.395 m → **Re_x ~= 1.42e5** (5.4 · 0.395 / 1.5e-5). Tolerance **0.20** (relative) — the
   accepted gamma-Re_theta onset-prediction band (Langtry & Menter 2009).
2. **`cf`** (pointwise, `normalized`): the full Cf(x) distribution, max error normalised by the
   peak Cf. Tolerance **0.25** — a documented curve-shape/magnitude band; the pointwise max is
   dominated by the steep transition region, so this is deliberately the secondary check.

## `u95_input`

The tabulated points carry no digitization uncertainty (verbatim from the tutorial). The
model-form band is captured by the tolerances above; a small `u95_input` (~5%) covers the
experimental scatter in the compiled T3 data.

## Tracking

Git-tracked scalar table (~0.4 KB; forward-regime convention). License: the tabulated data
travels with the GPL-3.0 OpenFOAM-ESI tutorial distribution; the underlying experimental data
is cited under fair use (Savill 1993/1996; Roach & Brierley).
