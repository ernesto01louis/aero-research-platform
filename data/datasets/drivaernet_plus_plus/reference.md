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
  https://dataverse.harvard.edu/dataverse/DrivAerNet (NOT Hugging Face).
- The DrivAerNet++ collection is **split into 5 sub-datasets** on
  Dataverse; each has its own DOI (probed via the Dataverse search API
  in the Stage-08 follow-up session 2026-05-31):

  | Sub-dataset | DOI | Size on Dataverse | What it has |
  |---|---|---|---|
  | **Annotations** | `doi:10.7910/DVN/CAWRXI` | **75 GB** (7 files) | smallest sub-dataset; summary metadata + per-car labels |
  | **Pressure** | `doi:10.7910/DVN/K7PWNJ` | **213 GB** (15 files) | surface pressure fields |
  | **Wall Shear Stress** | `doi:10.7910/DVN/PCZYL4` | **436 GB** (15 files) | wall-shear-stress fields |
  | **3D Meshes** | `doi:10.7910/DVN/OYU2FG` | **443 GB** (15 files) | STL surface meshes — Stage-09 DoMINO trains on these |
  | **CFD** | `doi:10.7910/DVN/EEYHUA` | **10.6 TB** (30 files) | full volume + surface field snapshots; far exceeds homelab TrueNAS — pull a sample only, or stage to S3 |

  **Sizes were probed via the Dataverse Native API in the Stage-08
  follow-up session (2026-05-31), not from the paper.** Earlier doc
  estimates ("~hundreds of MB", "~800 GB") were wrong; trust this
  table.

  The ``AERO_DRIVAERNET_DOI`` env var takes ONE DOI per script run;
  loop over the ones you need. The script's hard-coded 1 TB free-space
  precondition was sized for a single ~800 GB pull from the paper's
  total-size description; it is too strict for Annotations alone and
  not strict enough to admit two large sub-datasets back-to-back —
  Stage 09 should revisit it.
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
├── LICENSE                          # CC-BY-NC-4.0 text
├── reference.md                     # this file
├── cases/                           # the bytes; mode depends on pull
│   ├── DrivAerNetPlusPlus_Cd_8k_Updated.csv       # lite (8,121 cars; Cd labels)
│   ├── DrivAerNetPlusPlus_CarDesign_Areas.csv     # lite (8,007 cars; frontal area)
│   ├── DrivAerNet_ParametricData.csv              # lite (4,166 cars; 24 design parameters)
│   ├── E_S_*.zip / F_S_*.zip / ...                # Dataverse (per sub-dataset)
├── splits/                          # canonical train/val/test partition
│   ├── train_design_ids.txt         # 5,818 IDs
│   ├── val_design_ids.txt           # 1,147 IDs
│   └── test_design_ids.txt          # 1,153 IDs
└── manifest.json                    # built by scripts/build_dataset_manifest.py
```

## Two pull modes

### Lite mode (default for Stage-08 baselines — ~2 MB)

Pulls only the **CSV summaries + canonical splits** from upstream's
Dropbox + GitHub paths (no Dataverse access, no guestbook flow). What
lands:

- `cases/DrivAerNetPlusPlus_Cd_8k_Updated.csv` — 8,121 cars × Cd
- `cases/DrivAerNetPlusPlus_CarDesign_Areas.csv` — 8,007 cars × frontal area (m²)
- `cases/DrivAerNet_ParametricData.csv` — 4,166 cars × 24 parametric design variables
- `splits/{train,val,test}_design_ids.txt` — canonical 5,818 / 1,147 / 1,153 split

```bash
ssh root@aero-build
cd /opt/aero/repo
AERO_ACKNOWLEDGE_NONCOMMERCIAL=1 \
AERO_DRIVAERNET_MODE=lite \
./scripts/download_drivaernet_plus_plus.sh
```

The lite pull is enough for **descriptor → Cd baselines** (MLPBaseline,
FNOSmoke, MGNSmoke smoke-grade only) once the manifest builder is
revised — see below.

### Full mode (Stage-09 DoMINO and beyond — Dataverse pull, multi-GB)

Uses the Dataverse Native API to pull a specific sub-dataset by DOI.
See sub-dataset table above for sizes.

```bash
AERO_ACKNOWLEDGE_NONCOMMERCIAL=1 \
AERO_DRIVAERNET_MODE=full \
AERO_DRIVAERNET_DOI="doi:10.7910/DVN/OYU2FG" \
AERO_DRIVAERNET_MIN_FREE_GB=500 \
./scripts/download_drivaernet_plus_plus.sh
```

**Dataverse Guestbook gate** — sub-datasets larger than the Annotations
set sit behind Dataverse's guestbook prompt (the Native API returns
`400 "You may not download this file without the required Guestbook
response"`). Upstream recommends **Globus** for the big pulls. A
Dataverse API token plus a one-time POSTed guestbook response is the
alternative; neither is wired into the script yet. **Stage 09 must wire
one of these in before any full pull.**

### Sub-dataset → DOI quick reference

The five sub-datasets and their DOIs are in the top-of-file table.

## Manifest builder gap — RESOLVED (Stage 09, ADR-012, option 3)

The loader's `DrivAerNetPlusPlusCase` schema previously expected
`body_length_m: float = Field(..., gt=0.0)` — an absolute body length in
meters. The lite pull's `DrivAerNet_ParametricData.csv` carries
`A_Car_Length` but **as a signed delta** from an undocumented baseline car
(values include negatives, e.g. `-37.6`), so an absolute length cannot be
computed honestly without the baseline.

**Stage 09 chose option 3** (the only data-independent fix): the loader
field is renamed `body_length_m → body_length_param` and the `gt=0.0`
constraint dropped, so it is honestly a *sign-neutral design parameter*,
not a length. The lite-mode `*Case` schema now validates the raw deltas.
(Options 1 — recover the baseline — and 2 — derive length from the 443 GB
3D-Meshes STL bounding boxes — remain available later if an absolute
length is ever needed; neither is required for DoMINO, which trains on
DrivAerML, not DrivAerNet++.)

The lite-mode manifest *builder*
(`scripts/build_dataset_manifest.py`'s `_LAYOUT["drivaernet_plus_plus"]`)
is still a pending entry: the lite pull is three CSVs (`*_Cd_8k_*`,
`*_Areas`, `*_ParametricData`), not the geo/force-moment two-CSV join the
builder does, so it needs the operator's first pull to confirm the exact
columns before the join is wired. `cases/` and `splits/` are the committed
source-of-truth meanwhile.

## Stage-08 baseline use

DrivAerNet++ is **not** trained on in Stage 08. The loader + quarantine
+ fence CI ship; the actual first training run is a Stage 09 decision
(and the cert will land with `non_commercial=True`).

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
