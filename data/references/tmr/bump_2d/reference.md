# TMR 2D Bump-in-Channel — Reference Data

**Case:** `bump_2d` — 2D bump-in-channel.
**Conditions:** Re = 3e6 (per unit length), M = 0.2, k-omega SST.
**Source:** NASA Turbulence Modeling Resource —
<https://tmbwg.github.io/turbmodels/bump_sst.html>
(the TMR site moved from `turbmodels.larc.nasa.gov` to `tmbwg.github.io`).

## Geometry

The lower-wall bump is the analytic surface

    y(x) = 0.05 * sin^4( pi * (x - 0.3) / 0.9 ) ,   0.3 <= x <= 1.2

(equivalently `0.05 * sin^4(pi*x/0.9 - pi/3)`) — zero and tangent to the flat
wall at x = 0.3 and x = 1.2, peak height 0.05 at x = 0.75; flat elsewhere.
Implemented in `aero.adapters.openfoam.tmr_geometry`.

## `cp.csv`, `cf.csv` — surface pressure and skin friction vs. x

Columns: `x`, `cp` / `cf`. Both are the **CFL3D SST** verification data,
extracted from `Bump/SST/{cp,cf}_bump_sst.dat` in the
[`TMBWG/turbmodels`](https://github.com/TMBWG/turbmodels) repository (the
first, "CFL3D", Tecplot zone; x ∈ [0, 1.5]).

The harness compares Cp pointwise (3%, `normalized`) and Cf pointwise (5%);
the GCI mesh sweep (`--mesh-sweep`) is a verification study and needs no
reference data.

## License

NASA TMR data is a US Government work, in the public domain. No NASA
endorsement implied.
