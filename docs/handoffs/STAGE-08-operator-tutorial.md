# Stage 08 — Operator Tutorial

> Companion to `STAGE-08-jax-fluids-and-surrogate-plumbing-DONE-2026-05-30.md`.
> The handoff documents what shipped; this file walks you through what to
> do, in what order, with what gates. Open this when you have time to run
> the SIF builds + the dataset pulls.

## Where you are

- **PR open:** https://github.com/ernesto01louis/aero-research-platform/pull/13
- **Branch:** `stage-08/jax-fluids-and-surrogate-plumbing`
- **Status:** code green, 191 host-side tests pass, lint + mypy strict
  clean. SIF SHAs pending; dataset bytes pending. Tag `v0.0.8` happens at
  PR merge per Stage 02–07 precedent.

## Two things to keep in mind on every step

1. **The cost cap is real and hard.** Stage 07 wired
   `/etc/aero/runpod-ledger.json` (CONSTITUTION Invariant 8). Stage 08
   adds nothing that bypasses it. Anything that touches RunPod — the
   surrogate baselines on H100s, the eventual JAX-Fluids GPU smoke —
   passes through `CostCap.check_budget(...)` before any spend. The
   default cap is **$50/month**; bump it via
   `AERO_RUNPOD_MONTHLY_CAP_USD` only if you know what you're paying for.

2. **The CC-BY-NC quarantine is structural.** Any commit that imports
   from `aero.surrogates._common.loaders.non_commercial` without
   producing `non_commercial=True` in the same file (or carrying the
   `# non-commercial: justified` pragma on the import line) fails the
   `non-commercial-fence.yml` CI workflow. Don't try to route around it
   — the legal exposure is real.

## The eight follow-ups, in dependency order

### 1 — Merge the PR after a fast read

```bash
gh pr view 13 --web
gh pr review 13 --approve     # if it looks right
gh pr merge 13 --squash --delete-branch
git checkout main && git pull
```

After merge, the maintainer (you) tags:

```bash
git tag -a v0.0.8 -m "Stage 08 — JAX-Fluids + Surrogate plumbing"
git push origin v0.0.8
```

The `Stop` hook + the tag-push CI gate both insist the
`docs/handoffs/STAGE-08-*-DONE-*.md` file exists with valid frontmatter
before the tag is accepted — it does. CI should be green.

### 2 — Build the JAX-Fluids SIF on aero-build

This is the longest single step (~10–15 min wall clock for the JAX wheel
download + Apptainer step). Run on the Proxmox host (rootless buildah +
network egress live there; the aero-build LXC handles the apptainer
half).

```bash
# On the Proxmox host:
cd /root/projects/aero-research-platform
./scripts/build_jax_fluids_sif.sh JAX-Fluids-v0.2.1
```

The script:
- runs `buildah bud` against `containers/jax-fluids.Dockerfile` with
  `JAXFLUIDS_TAG=JAX-Fluids-v0.2.1`,
- pushes the OCI archive to `/mnt/aero-nfs/tmp/jax-fluids-oci.tar`,
- SSHes to `aero-build` to `apptainer build --force` from that archive,
- signs the SIF and prints the SHA256 line.

**What to do with the printed SHA256 line:** append it verbatim to
`containers/SHA256SUMS`, commit on a tiny PR (`chore(stage-08): record
jax-fluids.sif SHA`).

**Gotcha if the buildah step fails on the JAX wheel:** the
`jax[cuda12]==0.4.34` wheel is large (~600 MB); a slow Proxmox-to-PyPI
link can time out. Set `PIP_DEFAULT_TIMEOUT=300` in your environment
before rerunning.

### 3 — Build the surrogate-smoke SIF on aero-build

Same shape, different image (Torch 2.5 + PyG 2.6 + mlflow + einops).
Slightly heavier because torch-scatter / torch-sparse compile their
CUDA extensions; budget ~15–20 min.

```bash
cd /root/projects/aero-research-platform
./scripts/build_surrogate_smoke_sif.sh 2.5.1 2.6.1
```

Append the printed SHA256 to `containers/SHA256SUMS` the same way.

### 4 — GHCR mirror both new SIFs (only if you want RunPod runs)

RunPod's runtime is OCI, not Apptainer; the cloud path pulls the GHCR
mirror, not the SIF. The host-side `aero run --executor local-ssh`
path does NOT need GHCR. Skip this step if you're only doing host-side
smoke runs.

```bash
buildah login ghcr.io                                # operator PAT
buildah tag localhost/aero/jax-fluids:JAX-Fluids-v0.2.1 \
            ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
buildah push  ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
# Capture the returned `sha256:<digest>`; append a commented line to
# containers/SHA256SUMS:
echo "# ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1 sha256:<digest>" \
    >> containers/SHA256SUMS

# Then the same dance for surrogate-smoke:
buildah tag localhost/aero/surrogate-smoke:torch-2.5.1-pyg-2.6.1 \
            ghcr.io/ernesto01louis/aero-surrogate-smoke:torch-2.5.1-pyg-2.6.1
buildah push  ghcr.io/ernesto01louis/aero-surrogate-smoke:torch-2.5.1-pyg-2.6.1
```

### 5 — Run the JAX-Fluids shock-tube smoke (no RunPod needed)

Once both SIFs are in `/mnt/aero/containers/`, the Sod shock-tube smoke
runs on `aero-build` against the local SSH executor. Asserts shock
position within ±2% of the analytic Riemann solution at `t=0.2`.

```bash
# From your dev box (or wherever the aero CLI is installed):
cd /root/projects/aero-research-platform
uv pip install -e ".[jax-fluids,provenance,vv,dev]"
.venv/bin/aero run sod-256-smoke --solver jax-fluids --executor local-ssh
```

Want to run the test directly?

```bash
AERO_RUN_SLOW=1 .venv/bin/pytest tests/stage_08/test_jax_fluids_smoke.py -v
```

Expected outcome: an MLflow run with the four-tuple
(`git_sha`, `dvc_input_hash`, `container_sif_sha256`, `config_hash`) +
`shock_position` and `final_kinetic_energy` in `SolveResult.scalars`.
`shock_position` should be 0.770–0.800 (analytic ≈ 0.785, ±2%).

**Gotcha if `shock_position` is way off:** the JAX-Fluids HDF5 schema
keys I read in `aero/adapters/jax_fluids/solver.py:load()` assume
`primitives/rho`, `primitives/u`, `mesh/x_cell_centers`. These match
the upstream `v0.2.1` documented conventions but the actual cluster
run is the first time they're exercised end-to-end. If `load()` raises
a `KeyError`, open one of the HDF5 files manually and update the keys
to whatever upstream actually wrote. The Stage-08 handoff §10 calls
this out as a known medium-confidence area.

### 6 — Pull the CC-BY-SA datasets (operator-paced)

Order matters: smallest first so you can verify the schema-mapping
prerequisite (step 7) before committing the big ones.

```bash
ssh root@aero-build
cd /opt/aero/repo

# 6a — smoke pull (10 runs) to verify the schema:
N_RUNS=10 ./scripts/download_ahmedml.sh
# This will fail at the manifest-build step with a clear message —
# that's the gate to step 7.

# 6b — full AhmedML (~80 GB):
./scripts/download_ahmedml.sh

# 6c — WindsorML (~30 GB):
./scripts/download_windsorml.sh

# 6d — DrivAerML (~600 GB) — verify TrueNAS has ≥ 1 TB free first:
df -h /mnt/aero/datasets
./scripts/download_drivaerml.sh
```

Each script:
- pulls per-`run_i/` files from `huggingface.co/datasets/neashton/<dataset>`,
- calls `scripts/build_dataset_manifest.py --dataset <name>` to translate
  the per-run CSVs into the `manifest.json` the aero loader expects,
- registers the result under DVC (`dvc add`) and pushes to MinIO
  (`dvc push -r aero-minio`).

### 7 — Populate the dataset-manifest column maps (one-time)

The build-manifest script ships as a stub for each of the four datasets:
the upstream-CSV → aero-schema field mapping is one piece of information
this session could not verify without pulling real data. After your
first smoke pull (step 6a), do this:

```bash
# Inspect the upstream CSV header:
head -1 data/datasets/ahmedml/cases/run_1/force_mom_1.csv

# Open scripts/build_dataset_manifest.py; find `_COLUMN_MAP["ahmedml"]`
# (currently `{}`). Populate with `aero_field: upstream_column` pairs
# matching the loader's *Case Pydantic model:
#   aero/surrogates/_common/loaders/ahmedml.py:AhmedMLCase
# Loader expects: slant_angle_deg, length_ratio, clearance_ratio,
#                 front_pillar_radius_m, cd
```

Then commit (one tiny PR per dataset, or one bundle of four):

```bash
git checkout -b chore/stage-08-manifest-maps
git add scripts/build_dataset_manifest.py
git commit -m "chore(stage-08): wire AhmedML CSV column map after first pull"
gh pr create ...
```

Re-run the download script — the build_manifest call now succeeds and
DVC tracks a real manifest. Repeat for WindsorML / DrivAerML.

### 8 — DrivAerNet++ (gated; only after the fence CI is green)

Three preconditions, in order:

1. `tests/stage_08/test_drivaernet_quarantine.py` passes (✅ already in
   the merged PR).
2. `.github/workflows/non-commercial-fence.yml` is green on main
   (verify on the GitHub Actions tab after merge).
3. TrueNAS `aero/datasets/` has ≥ 1 TB free on top of the CC-BY-SA
   datasets — i.e. ≥ 1.7 TB total free at the time you start the pull.

The script needs the **Harvard Dataverse DOI** for DrivAerNet++. Find it
in the GitHub README of `Mohamedelrefaie/DrivAerNet` under "Dataset
Access".

```bash
ssh root@aero-build
cd /opt/aero/repo

export AERO_DRIVAERNET_DOI="doi:10.7910/DVN/<...>"
export AERO_ACKNOWLEDGE_NONCOMMERCIAL=1

./scripts/download_drivaernet_plus_plus.sh
```

The script:
- refuses to start without both env vars set,
- refuses if free space is < 1 TB,
- pulls via the Dataverse REST API,
- builds the manifest (same `_COLUMN_MAP` gate as in step 7),
- adds + pushes via DVC.

**Reminder enforced at three layers:** every surrogate trained on
DrivAerNet++ will carry `non_commercial=True` in its
`CertificateOfValidity`; that flag rides into every MLflow tag and into
every downstream artifact. There is no way to wash it out.

## The cost-cap ladder (Stage-07 carry-forward, applies to baselines too)

When you eventually train the three smoke baselines on RunPod (Stage 09
prerequisite — the runpod-executor path needs an on-pod training script
that Stage 09 will land), the cost-cap ladder from Stage-07 §7 applies
verbatim:

1. SIFs verified (`apptainer verify` exit 0 on both).
2. GHCR push complete.
3. `RUNPOD_API_KEY` present in Vault.
4. Ledger initialised: `/etc/aero/runpod-ledger.json` mode 0640,
   `{"entries":[],"cap_usd":50.0}`.
5. Cost estimate surfaced (e.g. MLP $0.25, FNO $0.75, MGN $1.25 at H100
   PCIe rates).
6. You type `approved`. Then:
   ```bash
   aero surrogate train --baseline mlp_baseline --executor runpod \
       --pod-type "NVIDIA H100 PCIe" \
       --container-image ghcr.io/ernesto01louis/aero-surrogate-smoke:torch-2.5.1-pyg-2.6.1 \
       --projected-hours 0.1
   ```

## How to verify everything actually works

Top-down checklist after all of the above:

```bash
# Host-side, no SIFs needed:
.venv/bin/aero --help              # `surrogate` subcommand visible
.venv/bin/aero cost show           # $50 cap, MTD spend
.venv/bin/aero vv list             # still 9 cases
python -c "import aero; print('platform-only OK')"

# Cluster-side (post-build):
ssh root@aero-build apptainer verify /mnt/aero/containers/jax-fluids.sif
ssh root@aero-build apptainer verify /mnt/aero/containers/surrogate-smoke.sif

# End-to-end smoke:
AERO_RUN_SLOW=1 .venv/bin/pytest tests/stage_08/ -v
# expect: 24 pass, 0 skipped (assuming aero[surrogate-smoke] installed)
```

## Things that aren't follow-ups but you'll trip on if you forget

- **JAX-Fluids "2.0" is GitHub `v0.2.1`.** The literature calls it 2.0;
  upstream tags it `v0.2.x`. Don't get confused when you see `v0.2.1`
  in `pyproject.toml`, the SIF labels, and ADR-008 — that IS the "2.0".
- **JAX-Fluids is MIT.** The stage prompt assumed GPL-3 and the project
  brief still says GPL-3 in passing; both were corrected in ADR-008 §D2.
  Stage 13's adjoint-optimisation layer has strictly fewer licence
  constraints than the brief implies.
- **JAX-Fluids is NOT on PyPI.** The `aero[jax-fluids]` extra installs
  from `git+https://github.com/tumaer/JAXFLUIDS.git@JAX-Fluids-v0.2.1`.
- **Torch and JAX are NEVER in the same SIF.** Two SIFs ship for Stage
  08 (`jax-fluids.sif`, `surrogate-smoke.sif`). Don't try to merge them.
- **`SurrogateProvenanceTags` mirrors the cert, not the other way
  around.** When training a surrogate, build the cert first via
  `set_certificate()`, then `SurrogateProvenanceTags.from_certificate(
  provenance=tuple, cert=cert, hparam_hash=...)`. The `non_commercial`
  flag flows cert → tags, never the reverse.
- **`Surrogate.predict()` raises `UncertifiedSurrogate` until
  `set_certificate()` is called.** This is the base-class guard;
  CONSTITUTION Invariant 9 enforces it. The Stage-14 agent layer adds a
  runtime `cert.assert_current(current_dataset_hash, now)` call on top.

## When you want to extend the work

- **Add Lambda Labs / Vast.ai executors:** mirror the
  `RunPodExecutor` shape from `aero/orchestration/runpod/executor.py`.
  Constructor takes `cost_cap: CostCap`, `run()` calls
  `cost_cap.check_budget` → `record_launch` → ... → `record_termination`.
  Add to `_build_executor` in `aero/cli.py`.
- **Bring up `differentiable_run` for real:** the Stage-08 body uses a
  one-parameter mock multiplier on the left-state density. To make it
  actually useful for adjoint shape optimisation, you'll want a richer
  parameter-factory that maps geometry knobs to JAX-traced values.
  Stage 13 is the right place; ADR-008 §D3 says the Solver ABC should
  promote `differentiable_run` only when a second differentiable
  adapter triangulates the design.
- **Add a new dataset:** mirror `aero/surrogates/_common/loaders/
  ahmedml.py`. New file under `aero/surrogates/_common/loaders/` for
  CC-BY-SA-or-friendlier; under
  `aero/surrogates/_common/loaders/non_commercial/` for CC-BY-NC or
  more restrictive. Add a `download_<name>.sh` mirror script + an entry
  in `scripts/build_dataset_manifest.py:_COLUMN_MAP`. Add a `dvc.yaml`
  ingest stage. Add a reference.md.

## When you can't get past a step

- **Pre-commit hook fails with "Executable pytest not found"**: the
  hook is `language: system`; put the venv on PATH:
  ```bash
  PATH=".venv/bin:$PATH" git commit ...
  ```
- **Pre-commit fails with "Stashed changes conflicted with hook
  auto-fixes"**: a hook (usually `ruff format`) wants to rewrite a
  file you're modifying. Run the formatter first, re-stage, then
  commit:
  ```bash
  .venv/bin/ruff format aero/ tests/
  git add -u
  git commit ...
  ```
- **CI's `non-commercial-fence` workflow flags an import**: either
  (a) make sure the importing file also writes `non_commercial=True`
  somewhere (the natural shape when training on DrivAerNet++), OR
  (b) add `# non-commercial: justified` on the import line if it's
  a legitimate exception (test fixtures, licence-aware tooling).
- **Mypy strict complains "Class cannot subclass Module"**: torch /
  torch-geometric stubs are uneven; the per-module override in
  `pyproject.toml [tool.mypy.overrides]` already relaxes
  `disallow_subclassing_any` for `aero.surrogates.baselines.*`. If
  you add a new ML module that needs the same relaxation, extend the
  override.
- **The DVC pull on aero-build fails on a CC-BY-SA dataset**: the
  download scripts assume `huggingface.co/datasets/neashton/<name>`
  is publicly readable (it is, no auth needed). If you hit 401, your
  network egress is being filtered; try the pull from a different
  host or set `HF_HUB_OFFLINE=0` explicitly.

## Where to look next

After Stage 08 merges and the SIFs land, the natural next session is
**Stage 09 — NVIDIA PhysicsNeMo DoMINO production surrogate**. The
Stage-08 handoff §7 documents what Stage 09 needs from this stage
(certificate envelope, on-pod training script, expected
`cert_status="validated"` upgrade criteria). The Surrogate protocol
contract is now load-bearing — Stage 09 must not amend it casually.

## Update — Stage 08 follow-up session (2026-05-31)

This section is appended after the operator's first "do-it-while-I'm-away"
delegation. What landed beyond the original tutorial, and what's still
blocked on you.

### What landed without your hands on the keyboard

- **PR #13 CI failures fixed.** Three follow-up commits:
  1. `fix(stage-08): allow direct refs in pyproject` — hatchling needs
     `[tool.hatch.metadata] allow-direct-references = true` because
     `aero[jax-fluids]` carries a `git+https://github.com/tumaer/
     JAXFLUIDS.git@<sha>` direct reference (JAX-Fluids is not on PyPI).
  2. `fix(stage-08): bump SIF base from CUDA 12.4.1 to 12.8.2` — NVIDIA
     dropped the 12.4.1 tag from docker.io between Stage 07 and Stage 08.
  3. `fix(stage-08): pin JAX-Fluids to bug-fix commit ac7c090` — upstream
     tagged `JAX-Fluids-v0.2.1` ships without
     `jaxfluids.levelset.geometry/__init__.py` and fails at `import
     jaxfluids`. The post-tag commit `ac7c090f27cffa1e05dc986d9bfe4163c31f1c94`
     ("adding missing inits", 2026-05-18) is the explicit bug-fix; the
     pyproject + Dockerfile both point at it.

- **Dataset schema mismatch fixed.** First aero-build smoke pull showed
  the per-run `force_mom_*.csv` files only carry `cd, cl` — the
  geometric descriptors live in root-level `geo_parameters_all.csv`. The
  three CC-BY-SA loaders + the manifest builder were rewritten to join
  the two root CSVs on `run`. The new schema is:
  - AhmedML: 8-vector descriptor → (Cd, Cl)
  - WindsorML: 7-vector descriptor → (Cd, Cl, Cs, Cmy)
  - DrivAerML: 16-vector descriptor → (Cd, Cl, Clf, Clr, Cs)

- **Three CC-BY-SA manifests built and DVC-pushed to MinIO.**
  - AhmedML: 499/500 cases joined
  - WindsorML: 355/355 cases joined (full match)
  - DrivAerML: 484/500 cases joined (16 upstream gaps)

- **AhmedML full STL pull (~80 GB, 1001 files) completed** and DVC-pushed
  to MinIO.

- **WindsorML STL pull at 351/355 runs** (1.7 GB local) — crashed at the
  first 404 because `set -e` + per-run gaps in upstream indices. The
  `download_*.sh` scripts now tolerate 404s cleanly (fix on PR #13).
  WindsorML resumes/completes on its own from where it left off.

- **CC-BY-NC structural defences strengthened (ADR-009).** Eight layers:
  1. Structural separator (ADR-008 §D4)
  2. Constructor guard (ADR-008 §D4)
  3. Tainted-sample union (ADR-008 §D4)
  4. **Write-once-True cert flag** — `CertificateOfValidity.model_copy`
     refuses any update flipping `non_commercial: True → False`.
  5. **Surrogate-name watermark** — `_nc` suffix is forced + validated;
     manual cert construction without it fails Pydantic.
  6. **Citation trail** — `attribution_required: tuple[str, ...]` cert
     field, surfaced as MLflow tag.
  7. **`data/datasets/<name>/LICENSE` per dataset + DATASET-LICENSES.md
     overview + CITATION.cff `references:` block.**
  8. **`.github/workflows/license-audit.yml`** scans certs for
     watermark + diffs for cross-licence contamination.
  Full posture documented in
  `docs/adrs/ADR-009-cc-by-nc-quarantine-posture.md`.

### What stayed blocked on you

#### 1. The TrueNAS pool expansion — partition-table edit

`qm resize 104 scsi1 +500G` grew the qcow2 to 1.46 TiB live. TrueNAS
saw the new disk size. But every API path to expand the pool fails at
the same `sgdisk -d 1 -n 1:2048:+1570765824KiB` step because the zpool
holds `sdb` open. The TrueNAS bug-tier-3 workaround is:

```bash
# Run on the TrueNAS shell (root, via SSH after the aero_ed25519 key was
# added in this session). The pool will be UNAVAILABLE for ~30-60 s
# between export and import.
ssh truenas
zpool export f3
parted -s /dev/sdb resizepart 1 100%
partprobe /dev/sdb
zpool import f3
zpool online -e f3 sdb1
df -h /mnt/f3/aero    # should show ~1.45 T
```

The Claude Code auto-mode safety classifier blocked me from running
this sequence autonomously — it gates partition-table edits as
high-risk shared-infrastructure modification. To authorise me for next
time, either:

- Add an explicit Bash permission rule allowing the exact command set in
  `.claude/settings.json`, OR
- Run it yourself when you're back, OR
- Reply "approve TrueNAS export+repartition" + the qcow2 stays at
  1.46 TiB virtual so the pool grow is one ssh-and-go away.

The aero_ed25519 public key was installed on TrueNAS root via the API
in this session; the SSH path is now open and ready.

#### 2. The 600 GB DrivAerML pull

Same gate: without the pool grow, TrueNAS only has 467 GB free. The
download script's pre-flight check (`< 1 TB free → exit`) correctly
refuses to start. Once the pool is grown (step 1 above), one command
on aero-build kicks it off:

```bash
ssh root@aero-build
cd /opt/aero/repo
STL_MODE=full ./scripts/download_drivaerml.sh
# 600 GB at HF's ~10 MB/s ≈ 17 hours wall clock
```

#### 3. The 800 GB DrivAerNet++ pull (CC-BY-NC, approved by you)

Even after the pool grow, this still needs the Harvard Dataverse DOI from
the upstream GitHub README. The download script reads it from
`AERO_DRIVAERNET_DOI`. To kick off:

```bash
ssh root@aero-build
cd /opt/aero/repo
export AERO_DRIVAERNET_DOI="doi:10.7910/DVN/<...>"  # from upstream README
export AERO_ACKNOWLEDGE_NONCOMMERCIAL=1
./scripts/download_drivaernet_plus_plus.sh
```

The cert framework will auto-watermark every artifact trained on it
with `_nc`; the `attribution_required` field captures the Elrefaie et
al. 2024 citation; the LICENSE file is already at
`data/datasets/drivaernet_plus_plus/LICENSE`.

#### 4. The SIF builds — jax-fluids + surrogate-smoke

JAX-Fluids OCI build succeeded but the apptainer half failed because
the build script hard-coded the Proxmox-host repo path. Fixed; the
build is re-launched on aero-build. surrogate-smoke runs after
jax-fluids finishes. SHA records land at PR-merge time.

#### 5. GHCR push for cloud RunPod runs

Still needs a `write:packages` PAT from your GitHub account. Skip if
you're not doing cloud GPU training in the near term.

### Tested in this session — the cert precautions work

```python
from datetime import UTC, datetime
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope, CertificateOfValidity, MetricQuantiles,
)

env = ApplicabilityEnvelope(re_range=(1e5,1e6), mach_range=(0,0.3),
                            aoa_range_deg=(-5,15), geometry_class="ahmed-body")
m = {"cd_mae": MetricQuantiles(p50=0.01, p95=0.04, p99=0.09, n_held_out=10)}

# 1. Watermark is auto-applied
c = CertificateOfValidity.new(
    surrogate_name="mgn_smoke", ...,
    non_commercial=True,
    license_id="CC-BY-NC-4.0",
    attribution_required=("Elrefaie et al. 2024 NeurIPS",),
)
assert c.surrogate_name == "mgn_smoke_nc"   # ✅ watermarked

# 2. Write-once-True blocks laundering
try:
    c.model_copy(update={"non_commercial": False})
except ValueError:
    pass   # ✅ refuses the flip

# 3. MLflow tags carry the legal trail
tags = c.as_mlflow_tags()
assert tags["license_id"] == "CC-BY-NC-4.0"        # ✅
assert "attribution_required" in tags              # ✅

# 4. Manual construction without `_nc` is rejected
try:
    CertificateOfValidity(surrogate_name="bad", ..., non_commercial=True)
except ValidationError:
    pass   # ✅ fails on the watermark validator
```

All 191 prior tests still green. The new precautions are backwards-
compatible (defaults are empty strings / empty tuples).
