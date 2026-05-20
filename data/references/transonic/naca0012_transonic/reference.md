# NACA 0012 transonic — reference data (Stage 06, ADR-006)

The published reference Cd for the canonical transonic NACA 0012 case
(M = 0.7, AoA = 1.49 deg, fully turbulent, Re ≈ 9e6) is

    Cd ≈ 0.0079

drawn from AGARD-AR-138 / Schmitt-Charpin (the standard transonic-airfoil
reference set). The SU2 tutorial repository reports a converged value of
0.0080 ± 0.0001 on its tutorial mesh, consistent with the AGARD figure.

The 5% comparison tolerance is wider than the TMR 3% (Stage 05) because

* transonic experimental data carries larger absolute scatter than
  subsonic CFD-vs-CFD verification; and
* the SU2 O-grid `aero/adapters/su2/mesh_writer.py` builds is generated
  analytically — the first Stage-06 build is not the grid-converged
  Cd mesh. Tighten in Stage-12 once a GCI mesh sweep on this case lands.

`cd.csv` lists the canonical reference Cd at the standard angle of attack.
`load_scalar_csv` reads it keyed on `aoa_deg`.
