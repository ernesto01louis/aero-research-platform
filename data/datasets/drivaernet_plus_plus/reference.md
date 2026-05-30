# DrivAerNet++ — QUARANTINED CC-BY-NC dataset (Stage 08, ADR-008 §D4)

> ## LICENCE BANNER
>
> This dataset is licensed **CC-BY-NC-4.0**. Artifacts trained on it carry
> the non-commercial constraint. **The loader is structurally quarantined**
> at `aero.surrogates._common.loaders.non_commercial` and requires explicit
> `acknowledge_noncommercial=True` at construction time.
>
> See ADR-008 §D4 for the three-layer defence rationale.

## Source

- Project page: https://github.com/Mohamedelrefaie/DrivAerNet
- Actual dataset host: **Harvard Dataverse** —
  https://dataverse.harvard.edu/dataverse/DrivAerNet (NOT Hugging Face;
  Stage-08's first draft of the download script had this wrong and the
  Stage-09 prerequisite step needs the canonical DOI from the GitHub
  README to populate ``AERO_DRIVAERNET_DOI`` before
  ``scripts/download_drivaernet_plus_plus.sh`` will run).
- Paper: Elrefaie, M. et al. (2024). *DrivAerNet++: A Large-Scale
  Multimodal Car Dataset with Computational Fluid Dynamics Simulations.*
  NeurIPS Datasets & Benchmarks Track.
- Licence: **CC-BY-NC-4.0** (Creative Commons Attribution-NonCommercial 4.0).

## Contents

4 000+ DrivAer-family vehicle geometries with steady-state RANS
solutions. Per case: surface mesh, surface fields (pressure, wall-shear
stress), integrated Cd. ~800 GB compressed.

## Layout under DVC

```
data/datasets/drivaernet_plus_plus/
├── manifest.json
├── cases/
└── reference.md
```

## Mirror procedure (operator follow-up — gated)

**Prerequisites before any bytes are pulled to TrueNAS:**

1. `aero/surrogates/_common/loaders/non_commercial/` test suite is green
   (Stage 08 `tests/stage_08/test_drivaernet_quarantine.py`).
2. `.github/workflows/non-commercial-fence.yml` is enabled and passing on
   the Stage-08 PR.
3. Operator has confirmed TrueNAS `aero/datasets/` has ≥ 1 TB free margin
   on top of the CC-BY-SA datasets.

Once gated:

```bash
ssh root@aero-build
cd /opt/aero/repo
# Set the canonical Harvard Dataverse DOI from the upstream README:
export AERO_DRIVAERNET_DOI="doi:10.7910/DVN/<...>"
export AERO_ACKNOWLEDGE_NONCOMMERCIAL=1
./scripts/download_drivaernet_plus_plus.sh
```

## Stage-08 baseline use

DrivAerNet++ is **not** trained on in Stage 08. The loader + quarantine +
fence CI ship; the actual first training run is a Stage 09 decision (and
the cert will land with `non_commercial=True`).

## Citation

```bibtex
@inproceedings{drivaernet_plus_plus_2024,
  title     = {DrivAerNet++: A Large-Scale Multimodal Car Dataset with CFD},
  author    = {Elrefaie, Mohamed and others},
  booktitle = {NeurIPS Datasets and Benchmarks},
  year      = {2024},
  note      = {CC-BY-NC-4.0; https://github.com/Mohamedelrefaie/DrivAerNet},
}
```
