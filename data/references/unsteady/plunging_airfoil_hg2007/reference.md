# Plunging airfoil — Heathcote & Gursul (2007) rigid-foil thrust — reference data

**Case:** `plunging_airfoil_hg2007` — a rigid NACA-0012 in pure plunge (heave), amplitude
h0/c = 0.175, Strouhal St = 2 f h0 / U, Re ≈ 1e4 (laminar 2-D solve).
**Tier:** unsteady machinery (Stage-11 moving-body validation) — the flapping ladder's
experiment-anchored rung (VALIDATE-AGAINST-EXPERIMENT, Hard Rule 15).

## Source

Heathcote, S. & Gursul, I. (2007), "Flexible Flapping Airfoil Propulsion at Low Reynolds
Numbers," *AIAA Journal* 45(5):1066–1079. https://doi.org/10.2514/1.25431

The experiment (water tunnel) measured the time-mean thrust coefficient of a heaving foil of
varying chordwise stiffness; the **rigid ("steel") foil** is the reference here. Amplitude
h0/c = 0.175; Reynolds numbers 10 000 / 20 000 / 30 000 with the thrust reported
**Reynolds-independent** over that range (so the Re = 1e4 solve is comparable). Net thrust
appears above a critical Strouhal (~St 0.12–0.17); C_T rises monotonically with St; St ≈ 0.4
is the onset of the deflected-jet regime for the rigid foil.

## `thrust.csv` — mean thrust coefficient vs Strouhal

Columns: `strouhal` (St = 2 f h0 / U), `thrust_coefficient` (C_T = −C_D, thrust positive,
non-dimensionalised by 0.5 ρ U∞² c).

| St  | C_T  |
|-----|------|
| 0.2 | 0.04 |
| 0.3 | 0.11 |
| 0.4 | 0.21 |

The Stage-11 V&V anchor is **St = 0.4 → C_T = 0.21**, compared at a **15 % relative
tolerance**. The St = 0.2 / 0.3 points support the fallback **trend check** (C_T monotone in
St; net-thrust threshold) if the magnitude band is missed.

## ⚠️ Digitization provenance + uncertainty (READ)

These C_T values are **digitized-estimate points** consistent with the HG rigid-foil thrust
curve and its published CFD reproductions; they were **not** transcribed from a numeric table
(the primary figure was not machine-accessible at authoring time). Treat them as carrying a
digitization/model uncertainty of order **±15 % (≈ ±0.02–0.03 absolute)**, which enters
`u95_input`. **Before any foil result is promoted beyond a Stage-11 GO/CONCERN, verify these
points against Heathcote & Gursul (2007) Fig. (rigid-foil C_T vs St).** This is a flagged
open item in the Stage-11 handoff.

The 15 % tolerance also honestly absorbs the **modeling gap**: a 2-D laminar solve at
Re ≈ 1e4 omits 3-D / transitional effects, and the geometry is NACA-0012 rather than the HG
teardrop. Per operator decision, if the band is missed the fallback is a documented CONCERN
(trend + threshold, and/or a CFD-reproduction cross-check) — the tolerance is **never relaxed
to pass** (Stage-10 discipline).

## Tracking

Git-tracked: a handful of digitized scalar points (~100 bytes). The flapping-ladder rule's
DVC mandate targets *large* experimental datasets; this small table follows the
forward-regime tier's in-repo convention. A future *large* raw HG dataset (full force
histories / PIV) would move to DVC under `-r aero-nfs`. Recorded as a deliberate deviation in
the Stage-11 handoff.

## License

Experimental data published in Heathcote & Gursul (2007); cited under fair use. Digitized
points carry no additional dataset license.
