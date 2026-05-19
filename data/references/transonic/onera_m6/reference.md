# ONERA M6 — reference data (Stage 06, ADR-006)

The ONERA M6 wing is the canonical 3D transonic wing benchmark:

    M = 0.84, AoA = 3.06 deg, Re ≈ 1.17e7 (based on the mean aerodynamic
    chord 0.64607 m); wing area 0.7587 m²; sweep 30 deg; taper 0.562.

Experimental Cp distributions at seven span stations
(η = 0.20, 0.44, 0.65, 0.80, 0.90, 0.95, 0.99) are published by
Schmitt & Charpin in ONERA TR-1 (1979); the canonical comparison plots
appear in the SU2 tutorial and in countless CFD verification papers.

Stage 06 ships this `reference.md` describing the data; the pointwise CSVs
(`cp_station_<eta>.csv`, columns `x_over_c,cp`) are DVC-tracked and
fetched with `dvc pull`. The `OneraM6` benchmark case (`aero.vv.transonic.
onera_m6`) raises `BenchmarkError` if `cp_station_0.44.csv` is absent so the
nightly `vv-transonic` workflow skips cleanly rather than producing a fake
green; the `aero vv run` CLI surfaces the missing-data state directly.

Mesh asset: `data/meshes/su2/onera_m6.su2` — the BSD-licensed mesh from the
SU2 tutorial repository (`su2code/SU2/Tutorials/compressible_flow/Turbulent_ONERAM6`).
See `data/meshes/su2/reference.md`.
