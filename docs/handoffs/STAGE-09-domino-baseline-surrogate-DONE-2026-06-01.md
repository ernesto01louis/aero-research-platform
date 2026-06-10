---
stage: 09
stage_name: "Stage 09 — DoMINO Baseline Surrogate (PhysicsNeMo)"
status: partial
date_started: 2026-06-01
date_completed: 2026-06-01
session_duration_hours: 6.0
claude_code_version: "headless session"
model: claude-opus-4-8
git_sha_start: "8b2739ffc5489d8f71b92eb41eba8e2b78d87c1d"
git_sha_end: "fcef13aeb9f28f7038bc6fde77e2b3e78b277e46"
stage_tag: v0.0.9
next_stage: 10
next_stage_name: "Stage 10 — V&V Debt Retirement + Output-Validity Bar"
---

# Stage 09 — DoMINO Baseline Surrogate (PhysicsNeMo) — DONE 2026-06-01

> Status **partial**: the entire host-side implementation is complete and
> verified (ruff + mypy `--strict` clean, 220 tests passing). The cluster/cloud
> deliverables — building/signing `physicsnemo.sif`, GHCR mirror, staging
> DrivAerML, the multi-day RunPod training, the `validated` cert, and the NAS
> migration — are operator-gated (Phase 2–4) and deferred, exactly the Stage
> 07/08 precedent (host-side green, GPU/cluster deferred).

## 1. Deliverables status

| # | Deliverable (from STAGE-09 bundle) | Status | Note |
|---|---|:-:|---|
| 1 | PhysicsNeMo SIF pinned + built; SHA in SHA256SUMS | ⚠️ | `.def`/build script + pin authored; build+sign is Phase 2 (NGC 20 GB pull) |
| 2 | `pip install -e .[surrogate-domino,dev]` works | ✅ | extra is `aero[physicsnemo-cu12]` (CONSTITUTION name; bundle's `surrogate-domino` reconciled) |
| 3 | DoMINO trains on RunPod with the eight tags | ⚠️ | on-pod entrypoint + CLI + cost-cap path done; the run is Phase 3 (budget-approved) |
| 4 | Predictor-Corrector applied; speedup logged | ⚠️ | `train_domino` runs baseline + PC + logs speedup; executes on the pod |
| 5 | Held-out Cd within 5% of CFD | ⚠️ | the gate is implemented (`promote_to_validated`); the number lands Phase 3 |
| 6 | `CertificateOfValidity` generated + committed | ⚠️ | built + logged as MLflow artifact by the on-pod script |
| 7 | `aero vv surrogate domino --baseline` passing report | ✅ | `aero/vv/surrogate/` + CLI; the live report is written on the pod |
| 8 | `surrogate-inference-smoke` weekly CI active | ✅ | added to `vv-scale-resolving.yml` (GPU-gated, non-required) |
| 9 | ADR committed | ✅ | ADR-010 (DoMINO), +ADR-011 (storage), +ADR-012 (signing) |
| 10 | Post-stage handoff | ✅ | this file |
| 11 | Tag `v0.0.9` | ❌ | after Phase 3 (real training evidence); status is `partial` |

Plus the operator-requested "make it clean" work (Part 3): doc-drift fixes,
xfail milestone tags, DrivAerNet++ `body_length` resolution, signing fix, and the
pluggable cloud-now/NAS-later storage backend + the NAS migration runbook.

## 2. Decisions made

- **NGC container, not build-from-CUDA** — `physicsnemo.sif` wraps
  `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08` (NVIDIA's recommended path,
  carries the PC recipe). Rejected: pip-install PhysicsNeMo onto a CUDA base
  (more brittle, no upstream-blessed image). ADR-010.
- **Swappable `DominoEngine`** — the PhysicsNeMo/torch GPU work is behind an
  injectable engine so the cert/taint/guard seams are host-testable with a fake.
  Rejected: lazy-import torch directly in the surrogate (un-testable host-side).
- **Surrogate validation de-conflated from solver V&V** — DoMINO's `validated`
  cert gates on held-out DrivAerML (Invariant 9), NOT the red NASA-TMR dashboard
  (Invariant 5). The `production` tier stays gated on the green dashboard.
  ADR-010. This is the model the bundle already assumes.
- **`physicsnemo-cu12` extra name** — kept the CONSTITUTION/00-CONTEXT name over
  the bundle's `surrogate-domino` (the bundle is the outlier). Flag if you want
  the rename.
- **Pluggable DVC storage = named remotes + Hydra pointer** — no new Python; flip
  cloud→NAS by config + Vault creds only. ADR-011.
- **Non-interactive signing via Vault-fed passphrase** — `scripts/_apptainer_sign.sh`
  pipes the passphrase to `apptainer sign`. Rejected: passphrase-less key
  (weakens at-rest). ADR-012.
- **DrivAerNet++ `body_length` option 3** — rename to `body_length_param`
  (sign-neutral), the only data-independent fix. ADR-012.

## 3. Deviations from the stage plan

- The bundle said "ADR-009" — already taken (Stage 08 CC-BY-NC). Used **ADR-010**.
- Extra named `physicsnemo-cu12`, not the bundle's `surrogate-domino`.
- Config path is `conf/surrogate/domino.yaml` (repo uses `conf/`, not `configs/`).
- The actual GPU training + cert number + NAS migration are deferred (partial) —
  they need operator-approved budget + the new NAS hardware.
- Scope was *widened* per the operator: Part 3 cleanup + the storage backend +
  the NAS runbook are not in the bundle but were explicitly requested.

## 4. Environment / dependency / schema changes

- `pyproject.toml`: `aero[physicsnemo-cu12]` populated (`nvidia-physicsnemo[cu12]
  ==1.1.0` proposed pin, `torch-geometric>=2.6`, `warp-lang>=1.4`); new mypy
  override `aero.surrogates.domino.*` (disallow_subclassing_any=false).
- Hydra: new `conf/storage/{cloud,nas,minio}.yaml` group + `- storage: cloud`
  default in `conf/config.yaml` — **shifts every `aero run` config_hash** (storage
  is now part of the hashed run context; intentional).
- `.dvc/config`: `aero-cloud` + `aero-nas` remotes added (default stays `aero-minio`).
- Schema: `DrivAerNetPlusPlusCase.body_length_m` (`gt=0.0`) → `body_length_param`.
- `containers/SHA256SUMS` reserves the `physicsnemo.sif` slot (digest appended in Phase 2).

## 5. CI/CD changes

- `vv-scale-resolving.yml`: new weekly `surrogate-inference-smoke` job (Mon cron),
  GPU-gated, non-required.
- No new required status checks. `non-commercial-fence` promotion to required is
  still an operator branch-protection step (Open items).

## 6. Gotchas discovered

- **NGC pull is ~20 GB** and per-host (aero-build AND the RunPod pod separately).
  Needs `apptainer remote login docker://nvcr.io` (NGC API key) + the buildah/
  apptainer scratch on `/mnt/pve/Storage` (the aero-buildah-storage role).
- **`--shm-size=1g` is mandatory** for PhysicsNeMo data loaders (DataLoader
  bus-error otherwise). Docker/RunPod needs the flag; apptainer shares host
  `/dev/shm`. See `containers/physicsnemo-run.sh`.
- **A full DrivAerML DoMINO train exceeds the $50/mo cap** — operator-approved
  per-run budget required (Invariant 8); the DrivAerML subset bounds it.
- **The PhysicsNeMo engine GPU methods are stubbed** (raise
  `DominoEngineUnavailable`) pending the first pod run — the DGL→PyG migration
  + the exact 25.08 DoMINO symbols are validated + patched there.
- **The `nvidia-physicsnemo` pip pin (1.1.0) is a proposal** — confirm against the
  25.08 container at first build (Hard Rule 8).

## 7. Open items for the next stage (and beyond)

**Operator decisions (propose-first gates) before the cluster/cloud phases:**
- Confirm the PhysicsNeMo container tag (25.08) + the `nvidia-physicsnemo` pip pin.
- Cloud S3 vendor for the `aero-cloud` remote (B2 / R2 / S3 / RunPod-volume MinIO).
- DrivAerML subset (which variants, train/val/test fraction + seed).
- Training budget (a per-run cap raise; multi-day H100 ≈ $67–191).
- Cert expiry (keep the 180-day default?).
- Whether to fold the TMR V&V hardening (NACA blunt-TE) in now or as its own pass.

**Phase 2 (build host):** apply `aero-buildah-storage`; `apptainer remote login
docker://nvcr.io`; `scripts/build_physicsnemo_sif.sh` → append the SHA; GHCR mirror;
**re-sign nekrs/jax-fluids/surrogate-smoke** via `_apptainer_sign.sh`; migrate the
signing key into Vault; `uv pip install -e .[provenance]` (dvc-s3) on the venvs.

**Phase 3 (cloud):** stage the DrivAerML subset to `aero-cloud`; `aero surrogate
train --baseline domino --executor runpod --projected-hours <approved>`; confirm
the `validated` cert + the `surrogate_vv` report; then **tag v0.0.9**.

**Phase 4 (NAS hardware):** execute `docs/runbooks/stage-09-nas-parallel-cutover.md`;
flip `conf/config.yaml` default `storage: cloud → nas`.

**Stage 10:** Transolver/FIGConvNet/X-MGN reuse `aero/vv/surrogate/` + the loader
+ the `SurrogateProvenanceTags` helper — promote any shared DoMINO data-loading to
`aero/surrogates/_common/` then.

**Stage 14:** the agent's DoMINO MCP tool must call
`surrogate.certificate().assert_current(...)` before `predict()` (Invariant 9).

## 8. Pointers for the next session

- **Read first:** this handoff; `STAGE-09-domino-baseline-surrogate.md` (bundle);
  ADR-010/011/012; `docs/runbooks/stage-09-nas-parallel-cutover.md`; the CLAUDE.md
  Stage-09 entry.
- **Do not re-read:** the Stage-08 surrogate plumbing (covered in CLAUDE.md).
- **Run first to verify the world (host-side):**
  `.venv/bin/python -m pytest tests/stage_09 tests/unit -q` ;
  `.venv/bin/mypy aero` ; `.venv/bin/ruff check aero scripts tests`. All green
  at git_sha_end.

## 9. Artifacts produced

- `aero/surrogates/domino/{__init__,model,training,certificate}.py` — DoMINO surrogate.
- `aero/vv/surrogate/compare_surrogate_cfd.py` — surrogate-vs-CFD cross-check.
- `aero/cli.py` — `aero surrogate train --baseline domino`, `aero vv surrogate`.
- `scripts/stage09_domino_train.py` — on-pod entrypoint.
- `containers/physicsnemo.{def,run.sh}` + `scripts/build_physicsnemo_sif.sh` +
  `scripts/_apptainer_sign.sh`.
- `conf/surrogate/domino.yaml` + `conf/storage/*` + `.dvc/config` remotes.
- `docs/adrs/ADR-01{0,1,2}-*.md` + `docs/runbooks/stage-09-nas-parallel-cutover.md`.
- `ansible/roles/aero-buildah-storage/` + `aero-apptainer` extension.
- `tests/stage_09/*` — host-side test suite.

## 10. Confidence / risk note

- **High confidence:** the host-side implementation — ruff + mypy `--strict` (81
  files) + 220 tests all green. The cert gate, taint propagation, storage switch,
  and compare logic are directly tested.
- **Medium confidence:** the PhysicsNeMo engine GPU seams (stubbed; validated on
  the first pod run — DGL→PyG drift is the live risk, the bundle warned of it),
  and the `nvidia-physicsnemo` pip pin.
- **Low confidence / bus factor:** the exact DrivAerML surface-mesh layout under
  `cases/` + the DoMINO input packing (operator confirms at first pod run); the
  cloud S3 vendor + the NAS S3 app's DVC-remote compatibility.
- **Outstanding risks:** the training cost (cap), the 20 GB NGC pulls, and the NAS
  cutover's NFS root-squash parity (breaks the signing-key escrow if mismatched).

## 11. Post-handoff addendum — operator decisions (2026-06-01)

After the handoff the operator resolved the propose-first decisions:

- **Push + draft PR** of the `stage-09/domino-baseline-surrogate` branch.
- **`aero-cloud` = a RunPod network volume** (no egress; co-located with the H100
  pods) — `conf/storage/cloud.yaml` + `.dvc/config` now use a LOCAL DVC remote on
  the volume mount, not S3.
- **Training budget: decide later** — Phase 3 training is held; everything else is
  prepped.
- **NACA 0012 blunt-TE folded in now** — `aero/adapters/openfoam/{schemas,geometry,
  case_writer}.py` + `aero/vv/tmr/naca0012.py` add the open-TE geometry + the
  blunt-TE C-grid (split TE vertex, base wall, collapsed base-wake wedge). Host-
  tested for structure (`tests/stage_09/test_naca0012_blunt_te_blockmesh.py`: sharp
  unchanged 8-block/32-vert; blunt 9-block/34-vert). The `aero run` path stays
  sharp; the V&V case is blunt. **The xfail on `tests/vv/test_tmr_naca0012.py`
  stays until the Phase-3 cluster mesh-sweep confirms the mesh is VALID AND Cd is
  within 3%** — the collapsed base-wake wedge is the candidate that may need
  iteration there (a 2D `empty`-patch degenerate cell; cluster-validate before
  relying on it).

## 12. Phase-2 execution + DrivAerML pull (2026-06-02)

Phase 2 (build host) and the DrivAerML data pull ran this session. Tag `v0.0.9`
remains deferred to Phase 3 (no training evidence yet).

**PhysicsNeMo SIF — built + signed.**
- `physicsnemo.sif` (15 GB) built on aero-build, apptainer-direct from the pinned
  `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08`. `%test` passed.
- Probe of the base settled two open items: it already bundles **physicsnemo 1.2.0,
  torch 2.8.0a0+nv25.06, torch-geometric 2.6.1, warp 1.8.1**. So (a) the `%post`
  `pip install` was REMOVED (redundant + the unprivileged LXC blocks `%post`
  network — no buildah two-step needed); (b) the `pyproject` pin was corrected
  `nvidia-physicsnemo==1.1.0` → **`==1.2.0`** (ADR-010 amendment).
- Signed with key `682F6145…`; `apptainer verify` passes; SHA
  `4e6ea371…` recorded in `containers/SHA256SUMS`.

**Signer bug fixed (ADR-012).** `_apptainer_sign.sh` only matched
`APPTAINER_SIGN_PASSPHRASE`/`SIF_PASSPHRASE`, but the Stage-02 interim
`/root/.config/aero/signing.env` uses **`AERO_SIGNING_PASSPHRASE`** — so it fell
back to an interactive prompt and hung the build's sign step. Fixed to accept that
name. `jax-fluids.sif` + `surrogate-smoke.sif` re-signed (were unsigned; nekrs was
already signed); their `SHA256SUMS` entries updated to the signed-artifact digests
(`125c3f2e…`, `a3ad846e…`).

**DrivAerML surface pull (STL + boundary VTP, 500 runs ≈ 0.78 GiB/run).**
- Lands on the TrueNAS NFS. **DVC refuses to `dvc add` a symlinked dir**, so the
  pull runs from a repo clone ON the NFS (`/mnt/aero/aero-dev-repo`): working tree
  + cache (`/mnt/aero/dvc-cache`, `cache.type=hardlink` → single copy) + the new
  `aero-nfs` LOCAL remote (`/mnt/aero/dvc-remote`) all on one filesystem.
- `download_drivaerml.sh` rewritten: `huggingface_hub.snapshot_download`
  (resumable, retry loop, `HF_HUB_DOWNLOAD_TIMEOUT=60`), `FILESET=surface` (volume
  `.vtu` excluded — the full set is ~31 TB). 10-run smoke validated the whole path
  (download → manifest → `dvc add` → `dvc push`). Manifest joins to **484 rows**
  (root `geo_parameters_all.csv` 500 / `force_mom_all.csv` 484).
- Full pull **COMPLETE (2026-06-03)**: 484/484 runs (STL + boundary VTP), ~353 GiB /
  5810 files, `dvc add` + `dvc push -r aero-nfs` done (cache+remote in sync), pointers
  committed in **8a495ff** (`cases.dir` md5 `27bfdbd931aca71be3c3a4bebbf8aac4`,
  `manifest.json` md5 `60638acc…`). Data lives at
  `/mnt/aero/aero-dev-repo/data/datasets/drivaerml/cases` (NFS) + the aero-nfs remote
  `/mnt/aero/dvc-remote`; ~369 GB free on the TrueNAS NFS afterwards. **Gotcha:** the
  pull silently HUNG once at ~99% on a dead HTTPS socket (CLOSE-WAIT, no bytes for
  ~10 h — it evaded `HF_HUB_DOWNLOAD_TIMEOUT`); `run_long` still showed "running".
  Killed + resumed cleanly (snapshot_download skips completed files). For Phase-3
  cloud staging, set an HF token and add a wall-clock watchdog around the download.
- `dvc.yaml`: the `ingest-drivaerml` repro stage was removed (a path can't be both a
  pipeline out and a `dvc add` `.dvc` out).

**Envelope review.** `geo_parameters_all.csv` confirms 500 morphs of ONE DrivAer
**notchback** baseline at zero yaw → `conf/surrogate/domino.yaml` `geometry_class`
is correct. The exact Re/reference-length is confirmed from the paper at cert-issue
time (Phase 3); the bracket stays generous until then.

**Deferred (Phase 3 / later):** GHCR mirror of physicsnemo (RunPod-pod prereq); the
Vault signing-key migration (signing already works via `signing.env`); the multi-day
H100 training + the `validated` cert + the `surrogate_vv` report; then tag `v0.0.9`.

**Gotchas for next session:** DVC + symlinked dirs (use a repo on the data's
filesystem); git "dubious ownership" on NFS files owned by `nobody` when running as
root (`git config --global --add safe.directory …`); the signer passphrase var name;
HF unauthenticated download throughput (set an HF token for Phase-3 cloud staging).

## 13. Phase-3 prep + cross-check (2026-06-03)

Cross-checked Phase 2 (clean: ruff/mypy/`225 passed`, PR #14 11/11 CI green) and
prepared Phase 3:

- **All SIFs verified SIGNED** on aero-build (`apptainer verify`) — incl. nekrs (the
  Stage-09 audit's "unsigned" note was wrong; corrected). Signing chain complete.
- **Real DoMINO API introspected** in the 1.2.0 SIF:
  `physicsnemo.models.domino.model.DoMINO(input_features, output_features_vol=None,
  output_features_surf, global_features=2, model_parameters=cfg)`; data via
  `physicsnemo.datapipes.cae`. CPU import works; running needs the GPU pod.
- `conf/storage/nfs.yaml` added (Hydra profile for the `aero-nfs` on-prem remote;
  `cloud`/`minio`/`nas` already had profiles) + a storage-switch test param.
- **The turnkey Phase-3 procedure is `docs/runbooks/stage-09-phase-3-domino-training.md`**:
  the one real dev task is wiring `PhysicsNeMoDominoEngine` (still a stub) against
  that API on the pod (adapt PhysicsNeMo's `examples/cfd/external_aerodynamics/domino/`),
  then image/registry-auth + data staging + the budget-gated training → `validated`
  cert + `surrogate_vv` → NACA blunt-TE mesh-sweep un-xfail → tag `v0.0.9`.

## 14. Scope-refocus close-out addendum (2026-06-10)

The operator refocused the platform as a **hypothesis-driven aerodynamic shape optimizer**
(flapping-wing flagship; riblets demoted to an example; the optimization loop is the
mission). Adopted via **ADR-013** (refocus), **ADR-014** (budget tiers), **ADR-016** (FSI
structural-solver strategy), and **ADR-015** (Constitution Invariants 10 + 11, on a separate
PR in 72 h review). Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` (reworked);
re-aimed map: `docs/handoff-bundle/README-handoff.md` (Stages 10–20).

**Effect on Stage 09 (annotations, not history rewrites):**
- **Phase 3 DoMINO training CANCELLED per ADR-013** — §1 deliverables 3, 4, 5, 6 and the §7
  Phase-3 items are superseded. The path trained on automotive data (DrivAerML), which the
  optimizer mission cuts (cross-domain transfer to wings is unproven; the own-data surrogate
  factory replaces it at Stage 16). No GPU spend ($67–191 avoided).
- **Stranded artifacts FROZEN, not deleted:** `aero/surrogates/domino/`,
  `scripts/stage09_domino_train.py`, the Phase-3 runbook, the signed 15 GB `physicsnemo.sif`,
  and the **484-run / ~353 GiB DrivAerML** subset on the `aero-nfs` remote stay in place.
  **DrivAerML disk reclaim is a separate propose-first decision (literal `approved`)** — ~369
  GB free on TrueNAS; ledgered.
- **NACA blunt-TE mesh-sweep EXTRACTED into Stage 10** — it was always V&V-hardening,
  mis-coupled to the surrogate stage. It is now a Stage-10 hard-go/no-go deliverable.
- **Phase 4 NAS cutover unchanged** (operator-owned). **Vault signing-key migration survives**
  (ADR-012).
- **Frozen-optional solvers:** SU2 (now the post-v0.1.0 adjoint seed), PyFR, NekRS,
  JAX-Fluids — kept, not invested in.

**Status stays `partial`** (cancelled ≠ delivered; Stage-05 precedent). `next_stage_name`
updated to "Stage 10 — V&V Debt Retirement + Output-Validity Bar". **Tag `v0.0.9` is
recommended** (handoff valid; the Phase-3-evidence deferral reason is voided by the
cancellation; the tag pins the last pre-pivot state + the adoption docs) — applied on the
operator's literal `approved`.
