# AhmedML — CFD benchmark over the Ahmed body (Stage 08, ADR-008)

## Source

- Landing page: https://caemldatasets.org/ahmedml
- Actual dataset host: **Hugging Face** — `huggingface.co/datasets/neashton/ahmedml`
  (publicly accessible; no HF token required for CC-BY-SA-4.0 files).
- Paper: Ashton, N. et al. (2024). *AhmedML: High-Fidelity Computational
  Fluid Dynamics Dataset for Incompressible, Low-Speed Bluff Body
  Aerodynamics.* https://arxiv.org/abs/2407.20801
- Licence: **CC-BY-SA-4.0** — derivative works must carry the same licence;
  no commercial restriction.

## Contents

500 geometric variations of the canonical Ahmed body (slant angle, length
scaling, ground clearance, front-pillar radius). Each per-run directory
on Hugging Face (``run_1/`` … ``run_500/``) contains:

- ``ahmed_<i>.stl`` — surface mesh in STL.
- ``force_mom_<i>.csv`` — integrated coefficients (Cd, Cl, Cm) and the
  per-run geometric descriptor values.
- Additional VTK / volume / boundary-condition files at the upstream root
  (see the Hugging Face landing page for the full file tree).

## Layout under DVC

```
data/datasets/ahmedml/
├── manifest.json         (top-level per-case descriptor table; DVC-tracked)
├── cases/                (per-case STL + VTK + solution files; DVC-tracked)
│   ├── case-0001/
│   ├── case-0002/
│   └── ...
└── reference.md          (this file)
```

The `manifest.json` is the small (~few-hundred-KB) file the
`AhmedMLDataset` loader actually parses; the per-case files are pulled on
demand by the Stage-09 DoMINO surrogate.

## Mirror procedure (operator follow-up)

Upstream serves via HTTPS with no auth. Mirror to MinIO `s3://aero-dvc`:

```bash
# On aero-build (has direct internet egress + DVC + MinIO creds):
ssh root@aero-build
cd /opt/aero/repo                                   # the deployed repo clone
./scripts/download_ahmedml.sh                       # ~80 GB compressed
# Tip: smoke first with N_RUNS=10 to verify CSV schema before pulling 500.
N_RUNS=10 ./scripts/download_ahmedml.sh
```

The download script pulls each ``run_i/`` directly from
``huggingface.co/datasets/neashton/ahmedml`` (per Ashton et al.'s
canonical script), then invokes ``scripts/build_dataset_manifest.py
--dataset ahmedml`` to translate the per-run CSVs into the
``manifest.json`` shape the aero loader expects. The manifest builder
fails loud if its ``_COLUMN_MAP['ahmedml']`` block has not been
populated with the upstream-CSV ↔ aero-schema mapping — a one-time
operator step after the first ``run_1/force_mom_1.csv`` lands and its
header row can be inspected.

Capacity guidance: AhmedML compresses to roughly **80 GB** on MinIO; the
TrueNAS ``aero/datasets/`` dataset should retain ≥ 200 GB free margin
after all four CC-BY-SA + CC-BY-NC sets land.

## Stage-08 baseline use

The `mlp_baseline` and `mgn_smoke` surrogates draw their training data from
this loader. Targets: integrated Cd. Features (MLP): the four-vector
`(slant_angle_deg, length_ratio, clearance_ratio, front_pillar_radius_m)`.
Features (MGN): surface mesh as a `torch_geometric.data.Data` graph.

## Citation

```bibtex
@article{ahmedml2023,
  title  = {AhmedML: A scale-resolving CFD dataset of the Ahmed-body},
  author = {Ashton, N. and others},
  year   = {2023},
  note   = {CC-BY-SA-4.0; https://caemldatasets.org/ahmedml},
}
```
