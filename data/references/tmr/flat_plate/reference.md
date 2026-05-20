# TMR Turbulent Flat Plate — Reference Data

**Case:** `flat_plate_te` — zero-pressure-gradient turbulent flat plate.
**Conditions:** Re = 5e6 (per unit length; the plate is 2 units long, so
Re_x runs 0 → 10e6), M = 0.2, fully turbulent, k-omega SST.
**Source:** NASA Turbulence Modeling Resource —
<https://tmbwg.github.io/turbmodels/flatplate_sst.html>
(the TMR site moved from `turbmodels.larc.nasa.gov` to `tmbwg.github.io`).

## `cf.csv` — local skin-friction coefficient vs. x

Columns: `x` (streamwise position; the plate runs 0 → 2), `cf` (local Cf).

This is the **CFL3D SST** verification data on the finest (545×385) TMR grid,
extracted from `FlatPlate/SST/cf_plate_sstv.dat` in the
[`TMBWG/turbmodels`](https://github.com/TMBWG/turbmodels) repository (the
first, "CFL3D", Tecplot zone; rows restricted to the plate, x ∈ [0.01, 2.0]).
The Stage-05 V&V harness compares pointwise from x = 0.1 back (dropping the
leading-edge Cf singularity) against the 5% tolerance (ADR-005).

## License

NASA TMR data is a US Government work, in the public domain. No NASA
endorsement implied.
