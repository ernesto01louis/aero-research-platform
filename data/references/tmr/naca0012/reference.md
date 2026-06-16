# TMR NACA 0012 — Reference Data

**Case:** `naca0012_verification` — NACA 0012 airfoil, drag verification.
**Conditions:** Re = 6e6 (chord), M = 0.15, AoA = 0 deg, fully turbulent.
**Solve closure:** k-omega SST (`CaseSpec.turbulence_model`, the only legal value).
**Source:** NASA Turbulence Modeling Resource (mirror) —
<https://tmbwg.github.io/turbmodels/naca0012_val.html>
(model pages `naca0012_val_sa.html`, `naca0012_val_sst.html`).

## `cd.csv` — total drag coefficient

Columns: `aoa_deg`, `cd`. Stage 05 verifies AoA = 0 deg only. Current value:
**Cd = 0.008120 at AoA = 0 deg**, tolerance 3% (ADR-005). The Stage-05 harness
compares the Richardson-extrapolated (grid-converged) Cd from a three-grid mesh
sweep against this value.

### Grid-converged values by model (NASA TMR, Re = 6e6, M = 0.15, AoA = 0)

| Model | CFL3D | FUN3D |
|---|---|---|
| Spalart-Allmaras (SA) | 0.00819 | **0.00812** |
| k-omega SST | **0.00809** | 0.00808 |

**Provenance note (Stage 10):** the committed `cd.csv` value **0.008120 is the
SA / FUN3D grid-converged total drag**, even though this case solves with
k-omega SST. The k-omega SST grid-converged value is **~0.00808–0.00809**. The
discrepancy is ~0.5% — well inside the 3% tolerance, so the GO/NO-GO outcome is
unaffected — but the reference is mislabeled relative to the solve closure.
**Reconciling `cd.csv` to the SST value (0.00809) is an operator decision**: it
touches a V&V-contract number and the `_CD_REFERENCE` constant in
`tests/vv/test_tmr_naca0012.py`, so it is flagged rather than changed unilaterally
in this session. The total Cd is also consistent with the Ladson experimental
drag (C. L. Ladson, *Effects of Independent Variation of Mach and Reynolds
Numbers on the Low-Speed Aerodynamic Characteristics of the NACA 0012 Airfoil
Section*, NASA TM-4074, 1988).

### Pressure / viscous decomposition

The TMR summary pages publish only the **total** Cd at AoA = 0 — **no Cdp/Cdv
split**. The friction-vs-pressure question (is the platform's skin friction
over-predicted, independent of the trailing-edge pressure-drag artifact?) is
therefore resolved by the platform's own measured decomposition (`forces`
function object -> `SolveResult.cd_pressure` / `cd_viscous`, Stage 10) compared
against the literature, not by this reference summary.

## License

NASA TMR data is a US Government work, public domain. No NASA endorsement
implied.
