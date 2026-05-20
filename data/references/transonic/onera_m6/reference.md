# ONERA M6 — reference data (Stage 06, ADR-006)

The ONERA M6 wing is the canonical 3D transonic wing benchmark:

    M = 0.8395, AoA = 3.06 deg, Re = 11.72e6 (based on the mean aerodynamic
    chord 0.64607 m); wing area 0.7587 m²; sweep 30 deg; taper 0.562.

Experimental Cp distributions at seven canonical span stations
(η = 0.20, 0.44, 0.65, 0.80, 0.90, 0.95, 0.99) are committed here as
`cp_station_<eta>.csv` (columns: `x_over_c,cp`). Each row is one pressure
tap on the ONERA M6 wind-tunnel model; both upper- and lower-surface taps
are present at most x/c locations, so the curve is not a function of x
alone — a future stage's `evaluate` extension may split upper vs. lower
via the discarded `Z/L` column (TMR file: `Onerawingnumerics_val/case_2308.dat`).

## Source

Pulled from the NASA Turbulence Modeling Resource (now hosted at
`TMBWG/turbmodels`), file `Onerawingnumerics_val/case_2308.dat` —
the Schmitt-Charpin / ONERA TR-1 (1979) experimental data, run 308.
Public-domain US government work (NASA Open Source Agreement).

Mirroring script (one-shot): see the in-tree shell history; pulled via
`gh api repos/TMBWG/turbmodels/contents/Onerawingnumerics_val/case_2308.dat`,
base64-decoded, then split-by-Section into per-station CSVs with a comment
header preserving the original TMR source line.

## Sections → eta mapping

The Tecplot `Section` column maps to the canonical η as:

| Section | η     | x/c points |
|--------:|------:|-----------:|
|       1 | 0.20  | 34         |
|       2 | 0.44  | 34         |
|       3 | 0.65  | 34         |
|       4 | 0.80  | 34         |
|       5 | 0.90  | 45         |
|       6 | 0.95  | 45         |
|       7 | 0.99  | 45         |

The `OneraM6` benchmark case (`aero.vv.transonic.onera_m6`) reads
`cp_station_0.44.csv` for its single pointwise check; Stage 12 may add the
other six stations as separate metrics once a 3D wing-slice extraction
lands host-side.

## Mesh asset

`data/meshes/su2/onera_m6.su2` — the BSD-licensed mesh from the SU2 tutorial
repository (`su2code/Tutorials/compressible_flow/Turbulent_ONERAM6/`).
DVC-tracked; pull with `dvc pull data/meshes/su2/onera_m6.su2`.
