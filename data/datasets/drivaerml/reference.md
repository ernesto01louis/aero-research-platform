# DrivAerML — Industrial-spec DrivAer CFD dataset (Stage 08, ADR-008)

## Source

- Landing page: https://caemldatasets.org/drivaerml
- Actual dataset host: **Hugging Face** —
  ``huggingface.co/datasets/neashton/drivaerml``.
- Paper: Ashton, N. et al. (2024). *DrivAerML: A high-fidelity CFD dataset
  for road-car aerodynamics.*
- Licence: **CC-BY-SA-4.0**.

## Contents

~500 DrivAer variants (notchback / fastback / estateback) with detailed
wheel and underbody treatment. Industrial-spec mesh resolution; the
surface mesh has ~1.5 M cells per case. Each case ships:

- Surface mesh (STL + VTK)
- Steady-state RANS solution: surface pressure, wall-shear stress
- Volume snapshot at the symmetry plane (CC-BY-SA companion data)
- Integrated coefficients: Cd, Cl, Cm, drag area (CdA)

## Layout under DVC

```
data/datasets/drivaerml/
├── manifest.json
├── cases/
└── reference.md
```

## Mirror procedure

See `data/datasets/ahmedml/reference.md`. **DrivAerML is the largest
CC-BY-SA dataset in the bundle — ~600 GB** compressed on MinIO. Operator
should confirm TrueNAS `aero/datasets/` has ≥ 1 TB free *before* pulling.

## Stage-08 baseline use

Held back for Stage 09 (DoMINO production training) — the first surrogate
expected to cert at `cert_status="validated"` against this dataset. Stage-08
loaders + DVC plumbing land; the actual `dvc pull` is a Stage-09 prologue.

## Citation

```bibtex
@article{drivaerml2024,
  title  = {DrivAerML: A high-fidelity CFD dataset for road-car aerodynamics},
  author = {Ashton, N. and others},
  year   = {2024},
  note   = {CC-BY-SA-4.0; https://caemldatasets.org/drivaerml},
}
```
