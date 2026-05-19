# NACA 0012 — Stage 03 walking-skeleton reference case

The single end-to-end case exercised by the Stage 03 walking skeleton:
STL-free geometry -> Apptainer OpenFOAM-ESI `simpleFoam` -> MLflow run ->
reported drag coefficient.

## Conditions

| Quantity | Value |
|---|---|
| Section | NACA 0012 (symmetric, 12% thickness) |
| Reynolds number (chord) | 6.0e6 |
| Mach number | 0.15 (low-speed; recorded, not used by incompressible `simpleFoam`) |
| Angle of attack | 0 deg |
| Turbulence model | k-omega SST (RAS) |
| Solver | OpenFOAM-ESI v2412 `simpleFoam` (steady, incompressible) |

## Expected result

Drag coefficient **Cd ≈ 0.0079** at zero incidence, dominated by skin
friction; lift **Cl ≈ 0** by symmetry. Reference: Ladson, C.L., *Effects of
Independent Variation of Mach and Reynolds Numbers on the Low-Speed
Aerodynamic Characteristics of the NACA 0012 Airfoil Section*, NASA TM-4074
(1988).

The Stage 03 smoke test accepts Cd within ±25% of 0.0079 — a deliberately
loose walking-skeleton band. Stage 05 tightens it against NASA Turbulence
Modeling Resource reference data.

## Geometry asset

`naca0012.csv` holds the upper-surface (x, y) coordinates, cosine-spaced,
generated analytically from the closed-trailing-edge NACA 4-digit equation
(`aero.adapters.openfoam.geometry.naca0012_coordinates`). It is fully
reproducible from `n_points` alone — there is no opaque binary.

No STL is stored: the Stage 03 mesh is a 2D `blockMesh` C-grid, which builds
the airfoil surface directly from this coordinate curve. An STL becomes
relevant only with `snappyHexMesh` / 3D cases (Stage 06+). See ADR-003.

## Provenance

This asset is committed in-tree for Stage 03. DVC tracking of
`data/references/` is wired in Stage 04, alongside the four-fold provenance
contract (`dvc_input_hash`, `config_hash`).
