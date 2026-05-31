# WindsorML — CFD benchmark over the Windsor body (Stage 08, ADR-008)

## Source

- Landing page: https://caemldatasets.org/windsorml
- Actual dataset host: **Hugging Face** —
  ``huggingface.co/datasets/neashton/windsorml``.
- Paper: Ashton, N. et al. (2024). *WindsorML: A scale-resolving CFD
  dataset of the Windsor-body.*
- Licence: **CC-BY-SA-4.0** — same conditions as AhmedML.

## Contents

~250 geometric variations of the Windsor body spanning yaw angle, ride
height, and rear-end geometry (notchback / fastback / estateback). Same
schema as AhmedML: surface mesh + RANS solution + integrated coefficients.

## Layout under DVC

```
data/datasets/windsorml/
├── manifest.json
├── cases/
└── reference.md
```

## Mirror procedure

See `data/datasets/ahmedml/reference.md` — identical pattern. WindsorML
compresses to roughly **30 GB** on MinIO.

## Stage-08 baseline use

Held back for Stage-09 / 10 cross-dataset generalisation studies; not the
primary training set for the Stage-08 smoke baselines (those use AhmedML).

## Citation

```bibtex
@article{windsorml2024,
  title  = {WindsorML: A scale-resolving CFD dataset of the Windsor-body},
  author = {Ashton, N. and others},
  year   = {2024},
  note   = {CC-BY-SA-4.0; https://caemldatasets.org/windsorml},
}
```
