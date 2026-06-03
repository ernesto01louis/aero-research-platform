# Runbook — Stage 09 Phase 3: DoMINO training → `validated` cert → tag v0.0.9

> Turnkey procedure for the Phase-3 DoMINO training run on rented GPU. Written
> after Phase 2 (SIF built+signed, DrivAerML pulled) and grounded in the **real**
> PhysicsNeMo 1.2.0 DoMINO API (introspected on aero-build, 2026-06-03). The one
> substantive dev task is wiring the real `PhysicsNeMoDominoEngine` — best done on
> the pod where it runs. Operator-gated on the **training budget** (Invariant 8).

## Prereqs already in place (Phase 2)

- `physicsnemo.sif` (15 GB, physicsnemo **1.2.0** / torch 2.8.0a0 / pyg 2.6.1 /
  warp 1.8.1) built + **signed** on aero-build; SHA `4e6ea371…` in `containers/SHA256SUMS`.
- **All SIFs signed + verified** (incl. nekrs — the Stage-09 audit's "unsigned"
  was wrong).
- DrivAerML surface subset: **484 runs, ~353 GiB (STL + boundary VTP)**, DVC-tracked
  on the `aero-nfs` remote (`/mnt/aero/dvc-remote`); pointers in `data/datasets/drivaerml/{cases,manifest.json}.dvc`.
- NGC API key in `/root/.config/aero/operator-secrets.env` as `NGC_API_KEY`.
- `pyproject` pin `nvidia-physicsnemo[cu12]==1.2.0`; `conf/surrogate/domino.yaml`
  envelope reviewed (DrivAer notchback, 484 morphs).

## Step 1 — Wire the real `PhysicsNeMoDominoEngine` (the core dev task; on the pod)

`aero/surrogates/domino/model.py:PhysicsNeMoDominoEngine` ships as a **stub** (its
methods raise `DominoEngineUnavailable`) by design — the real impl needs the GPU +
data to validate. The introspected 1.2.0 API to wire it against:

- **Model:** `from physicsnemo.models.domino.model import DoMINO`
  `DoMINO(input_features: int, output_features_vol: int | None = None,
  output_features_surf: int | None, global_features: int = 2, model_parameters=<cfg>)`.
  Surface-only DoMINO → `output_features_vol=None`, `output_features_surf` = #surface
  fields (e.g. pressure + 3 wall-shear = 4); `model_parameters` is the example's cfg.
- **Data:** `physicsnemo.datapipes.cae` (the CAE/external-aero datapipe) reads the
  per-case STL + boundary VTP from `cases_root` and builds the point-cloud input +
  surface-field targets. Mirror PhysicsNeMo's reference recipe.
- **Reference recipe:** adapt PhysicsNeMo's
  `examples/cfd/external_aerodynamics/domino/` (`train.py` baseline + its
  Predictor-Corrector variant + `conf/config.yaml` for bbox/sampling/normalisation)
  into the engine methods:
  - `train(...)` → the no-PC baseline loop.
  - `fine_tune_predictor_corrector(...)` → the PC recipe (`Y = Y_predictor + Y_corrector`).
  - `held_out_abs_errors(...)` → predict on the val split, **integrate surface
    pressure → Cd** (+ Cl/Cm), compare to the manifest `force_mom` values → per-target
    abs errors (the cert's `cd_mae`).
  - `predict_coefficients(surface)` → run the net on one packed surface → integrate.
  - `pack_surface(case_id, cases_root)` → the on-pod script's `_build_vv_cases`
    calls this (add it to the engine): read the case STL+VTP → DoMINO input.
  - `save_checkpoint(handle, path)` → `torch.save` state_dict + scalers.
  The host-side seams (cert/taint/guard/split) are already tested — only these GPU
  methods are new. Iterate them on the pod against a 10-run subset first.

## Step 2 — Container image + registry auth + pod bootstrap

`physicsnemo:25.08` is a **public NGC image**, so a GHCR mirror is **optional**:
- **Option A (no mirror):** point the pod at `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08`
  directly — needs RunPod configured with **NGC registry creds** (`$oauthtoken` /
  `NGC_API_KEY`).
- **Option B (GHCR mirror):** keep `conf/surrogate/domino.yaml`'s
  `container_image: ghcr.io/ernesto01louis/aero-physicsnemo:25.08`; push the image
  with `CR_PAT` and give RunPod GHCR creds.
Either way the pod image has PhysicsNeMo but **not** the aero repo, so the pod
bootstrap (before `scripts/stage09_domino_train.py`) must: clone aero @ the
stage-09 SHA, `pip install -e . --no-deps` (deps are in the base), and stage the
data (Step 3). Note: `RunPodExecutor` does not yet pass registry creds — add that
or pre-configure them on the RunPod account (a small Phase-3/Stage-13 tweak).

## Step 3 — Get DrivAerML onto the pod

The on-prem `aero-nfs` copy can't be NFS-mounted by a cloud pod. Choose:
- **A — DVC via a cloud remote:** push the DVC cache to `aero-cloud` (the RunPod
  network volume) from an aero LXC, then on the pod `storage=cloud` →
  `dvc pull -r aero-cloud`. (Add `HF`-free, no re-download.)
- **B — Re-pull from HF on the pod:** `download_drivaerml.sh` with **an HF token**
  (`HF_TOKEN`) + a **wall-clock watchdog** (Phase-2 gotcha: the unauth'd pull hung
  at 99% on a dead socket past `HF_HUB_DOWNLOAD_TIMEOUT`).
- To train from the **on-prem** copy instead (an aero LXC with a local GPU, if one
  ever exists), select `storage=nfs` (`conf/storage/nfs.yaml`, added this session).

## Step 4 — Run the training (budget-gated)

A full 484-run DoMINO train (multi-day H100) ≈ **$67–191** — **exceeds the $50/mo
cap**; raise the per-run cap or scope a subset first:
```bash
export AERO_RUNPOD_MONTHLY_CAP_USD=250   # operator-approved per-run
aero surrogate train --baseline domino --executor runpod \
  --pod-type "NVIDIA H100 PCIe" --projected-hours <approved> \
  --container-image <nvcr or ghcr ref>
```
Cost-cap (Invariant 8) gates the launch; `aero cost show` reconciles. The on-pod
`scripts/stage09_domino_train.py` runs dvc pull → baseline + PC → cert → 8 MLflow
tags → checkpoint → `surrogate_vv`.

## Step 5 — Validate, un-xfail, tag

- Confirm held-out **Cd MAE p95 < 5%** → `promote_to_validated()` issues the
  `validated` cert; `surrogate_vv` report logged. Issue the cert's exact Re /
  reference-length from the DrivAerML paper (arXiv 2408.11969) at this point.
- **NACA blunt-TE mesh-sweep** (CPU cluster, separate): `aero vv run --case
  naca0012_verification --mesh-sweep` on aero-build → if the blunt-TE mesh is valid
  AND Cd within 3%, remove the `xfail` from `tests/vv/test_tmr_naca0012.py` (never
  relax tolerance). If the collapsed base-wake wedge meshes badly, iterate the
  topology (handoff §11).
- Write the Phase-3 handoff addendum; **tag `v0.0.9`** (Hard Rule 10 — the handoff
  exists). Mark PR #14 ready-for-review.

## Phase-2 gotchas to carry forward

- DVC refuses to `dvc add` a symlinked dir → run from a repo on the data's
  filesystem (Phase 2 used `/mnt/aero/aero-dev-repo`).
- git "dubious ownership" on NFS files owned by `nobody` when root →
  `git config --global --add safe.directory <path>`.
- `warp` logs a CUDA-driver error on CPU import (harmless for introspection; the
  pod has a real driver).
- The signer reads `AERO_SIGNING_PASSPHRASE` (Phase-2 fix); keep that var set.
