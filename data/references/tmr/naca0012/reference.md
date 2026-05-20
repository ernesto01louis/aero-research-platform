# TMR NACA 0012 — Reference Data

**Case:** `naca0012_verification` — NACA 0012 airfoil, drag verification.
**Conditions:** Re = 6e6 (chord), M = 0.15, AoA = 0 deg, k-omega SST.
**Source:** NASA Turbulence Modeling Resource —
<https://turbmodels.larc.nasa.gov/naca0012_val.html>

## `cd.csv` — total drag coefficient

Columns: `aoa_deg`, `cd`. Stage 05 verifies AoA = 0 deg only.

Reference Cd = **0.008120** at AoA = 0 deg. This is the grid-converged
k-omega SST total drag for the NASA TMR NACA 0012, consistent with the
CFL3D / FUN3D family-0 results (~0.0081-0.0082) and with the Ladson
experimental drag (C. L. Ladson, *Effects of Independent Variation of Mach
and Reynolds Numbers on the Low-Speed Aerodynamic Characteristics of the
NACA 0012 Airfoil Section*, NASA TM-4074, 1988).

The Stage-05 harness compares the Richardson-extrapolated (grid-converged)
Cd from a three-grid mesh sweep against this value, tolerance 3% (ADR-005).

## License

NASA TMR data is a US Government work, public domain. No NASA endorsement
implied.
