# Laminar NACA 0012 (Re = 1000) — Reference Data

**Case:** `laminar_airfoil_naca0012` — NACA 0012, *laminar*, AoA = 0.
**Conditions:** Re = 1000 (chord), M = 0.1, laminar (no turbulence model), sharp
TE. **Tier:** forward-regime credibility — the low-Re airfoil baseline of the
flapping-validation ladder (`.claude/rules/flapping-validation-ladder.md`).
Transition modelling is Stage 13; this is the laminar baseline.

## Two metrics

### `cl` — lift coefficient (symmetry, reference-free)

A symmetric airfoil at zero incidence produces **zero lift**. A converged
symmetric solve must return `Cl ~= 0` (absolute tolerance 0.01). This is a
rigorous solution-quality check with no external reference — it catches spurious
asymmetry from the mesh or an under-converged solve.

### `cd.csv` — total drag coefficient (low-Re literature sanity)

Columns: `aoa_deg`, `cd`. **Reference Cd = 0.12 at AoA = 0**, from:

> D. F. Kurtuluş, *On the Unsteady Behaviour of the Flow around NACA 0012
> Airfoil with Steady External Conditions at Re = 1000*, Int. J. Micro Air
> Vehicles 7(3):301-326 (2015).

At Re = 1000, AoA = 0 the flow is **steady** (laminar, attached; vortex shedding
onsets only at AoA >= ~9 deg at this Reynolds number, per Kurtuluş), so a
steady-state solve is appropriate. Low-Re airfoil Cd carries a genuine
code-to-code / mesh spread (~±10% across published CFD), so the tolerance is
**10%** — a documented contract reflecting that spread, not a precision claim.
A solve landing outside the band is investigated (mesh, domain, TE treatment),
never relaxed.

## License

Reference value is a single published figure used under fair-use citation; no
dataset license applies. The Cl = 0 expectation is exact by symmetry. No
endorsement implied.
