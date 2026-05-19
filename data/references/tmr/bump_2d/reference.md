# TMR 2D Bump-in-Channel — Reference Data

**Case:** `bump_2d` — 2D bump-in-channel.
**Conditions:** Re = 3e6 (unit reference length), M = 0.2, k-omega SST.
**Source:** NASA Turbulence Modeling Resource —
<https://turbmodels.larc.nasa.gov/bump.html>

## Geometry

The lower-wall bump is the analytic surface

    y(x) = 0.05 * sin^4( pi * x / 1.5 ) ,   0 <= x <= 1.5

(zero and tangent to the flat wall at both ends, peak height 0.05 at
x = 0.75). Implemented in `aero.adapters.openfoam.tmr_geometry`.

## Reference data status (Stage 05)

The 2D bump is delivered with **two distinct kinds of check**:

* **Verification (GCI)** — `aero vv run --case bump_2d --mesh-sweep` runs a
  three-grid Grid Convergence Index study. A GCI compares the solution against
  itself at three resolutions, so it needs **no external reference data** and
  is fully exercised in Stage 05.
* **Validation (Cp / Cf vs. TMR)** — comparing the pointwise pressure and
  skin-friction distributions against the TMR-published CFL3D / FUN3D data
  requires those data files. The Stage-05 build host had no outbound network
  access, so `cp.csv` / `cf.csv` could not be mirrored. Fetching them from the
  URL above and dropping them here is a documented open item — see the
  Stage-05 handoff. Until then the bump *validation* test is skipped (the
  *verification* mesh sweep is not).

## License

NASA TMR data is a US Government work, public domain. No NASA endorsement
implied.
