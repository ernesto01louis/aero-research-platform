# CLAUDE.md — aero-research-platform

> Auto-loaded by Claude Code at session start. This file is the **first
> layer** of the four-layer memory model (CLAUDE.md → `.claude/rules/<topic>.md`
> → `STAGE-NN-*.md` → `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`). Read it,
> then the previous stage's handoff, then the current stage prompt.
> A stale CLAUDE.md misleads every future session — update it whenever
> reality diverges.

## What this project is

`aero-research-platform` is a fully open-source, peer-review-grade,
hardware-agnostic research platform for computational aerodynamics. The
final state spans classical CFD (OpenFOAM-ESI, SU2, PyFR, NekRS),
differentiable CFD (JAX-Fluids 2.0), ML surrogates (NVIDIA PhysicsNeMo —
DoMINO, Transolver, FIGConvNet, X-MeshGraphNet, MoE), multi-physics
coupling (preCICE 3 — flapping wing, vibrating skin, conjugate heat
transfer), V&V automation (NASA TMR, AIAA DPW-7, HLPW-5, ERCOFTAC), UQ via
UQpy+Dakota, multi-cloud GPU orchestration (RunPod / Lambda Labs /
Vast.ai), agentic CAE (NVIDIA NeMo Agent Toolkit + AI-Q Blueprint fork),
and literature mining (arXiv + Semantic Scholar + OpenAlex via pgvector).

The platform is built session-by-session against a staged handoff bundle
of **16 stages**, one Claude Code session per stage. The current stage is
named in `.aero-stage` at the repo root.

## The four-layer memory model

1. **CLAUDE.md** (this file) — invariants every session
2. **`.claude/rules/<topic>.md`** — path-scoped lazy-loaded rules
3. **`STAGE-NN-<name>.md`** — the current session's work-of-record
   (operator pastes at session start)
4. **`docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`** — the previous session's
   exit notes

## Session-start checklist

Every fresh session, read in this order:

1. `CLAUDE.md` (this file — auto-loaded)
2. `.aero-stage` (one line; tells you which stage you are in)
3. `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md` — previous stage's exit notes
4. The operator-pasted `STAGE-NN-*.md` (current stage prompt)
5. Any `.claude/rules/*.md` rule whose topic matches the work

Then begin work.

## Five non-negotiable principles

1. **Reproducibility first.** Every published number traces to a four-tuple
   `(git_sha, dvc_input_hash, container_sif_sha256, config_hash)`.
2. **Compute is fungible.** No code path may assume a specific backend
   (LXC, RunPod, Lambda Labs, Vast.ai, future on-prem Slurm).
3. **Solvers are containers.** Apptainer SIFs for HPC; OCI images for
   cloud. Digests in the provenance record.
4. **ML augments, never replaces, validated physics.** A surrogate is
   admissible only with a published `CertificateOfValidity` below
   threshold.
5. **GPL is fine.** GPL-3 / LGPL-3 / Apache-2.0 / BSD-3 only. No
   proprietary blobs.

## Hard rules — IMMUTABLE; override any conflicting stage prompt

1. **PLATFORM-NOT-HUB.** `aero/` core imports only stdlib + numpy +
   pydantic. Solver/ML/cloud deps live behind optional extras.
2. **FAIL-LOUD.** Pydantic strict (`extra='forbid'`). No silent fallbacks.
3. **PROVENANCE FROM DAY ONE.** Every run logs the four-tuple to MLflow
   tags. No exceptions.
4. **CONVENTIONAL COMMITS + CONVENTIONAL COMMENTS.** Commit format
   `<type>(stage-NN): <subject>`. Review labels per
   [Conventional Comments](https://conventionalcomments.org/).
5. **PROPOSE FIRST, EXECUTE LATER** for destructive ops. Wait for the
   literal word `approved` from the operator before: deleting files
   outside `/tmp`, force-pushing, dropping Postgres tables/roles/DBs,
   destroying Proxmox LXC/VM, modifying `/etc/pve/` or
   `/etc/network/interfaces` on the host, exceeding the cloud-GPU cost
   cap, deploying changes to any production-tier workflow.
6. **NO `--no-verify`. NO `--dangerously-skip-permissions`** outside
   ephemeral containers. Pre-commit and Claude Code hooks are not
   optional; if a hook is wrong, fix the hook.
7. **NO SECRETS** in code, this file, handoffs, commits, MLflow tags,
   PR descriptions, container layer history, or CI logs. Vault is the
   only persistence; `.env` (mode 0600) is local-dev convenience only.
8. **PIN HEAVY DEPS** exactly (PhysicsNeMo container tag, OpenFOAM
   release, SU2 git commit, etc.); document every pin in an ADR.
9. **DOCS MATCH REALITY.** README `## Status` is auto-regenerated from
   the latest post-stage handoff frontmatter; hand-editing it fails CI.
10. **POST-STAGE HANDOFF MANDATORY.** No `v0.0.NN` tag without
    `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md` existing with
    valid frontmatter (the `Stop` hook in `.claude/settings.json`
    enforces this in-session; CI enforces it on tag push).
11. **DO NOT TOUCH PRE-EXISTING NON-AERO INFRASTRUCTURE.** The Proxmox
    host runs many other workloads (LXCs 101-114, 200-207 except where
    explicitly listed below; VMs 100, 104, 111, 112). The aero stack
    provisions only NEW `aero-*` LXCs and shares read/write access only
    to the explicitly-listed application-agnostic services (existing
    Postgres LXC 202, Grafana LXC 205, Tempo LXC 204, Redis LXC 203,
    TrueNAS VM 104 via NFS). Nothing in the existing fleet may be
    reconfigured, restarted, or repurposed without explicit operator
    approval. **LXC 207 `aero-research` is pre-existing — leave it
    alone.** **The renamed `aero-orchestrator-consumer` GitHub repo and
    its local clone at
    `/root/projects/aero-research-platform.PRIOR-REMOTE-CLONE-do-not-touch/`
    are not part of this project — do not modify.**

## How to ask vs how to act

- **Ambiguity in deliverables** → ask via `AskUserQuestion`.
- **Choice between two reasonable patterns** → propose both with
  tradeoffs.
- **Refactor outside scope** → STOP and ask.
- **Destructive op** → propose, wait for `approved`.
- **Anything touching a pre-existing non-aero LXC/VM** beyond the
  explicitly-shared services above → STOP, propose, await `approved`.

## Stage-specific knowledge added incrementally

Subsequent stages append topic-specific guidance here. As of Stage 01:

- **SSH alias convention** (Stage 02) — the seven aero LXCs are reached as
  `aero-build`, `aero-dev`, `aero-mlflow`, `aero-vv`, `aero-prefect`,
  `aero-agent`, `aero-lit` (defined in `~/.ssh/config.d/aero` on the Proxmox
  host; default user `aero-admin`, `ssh root@aero-<name>` for break-glass).
  Full scheme: `docs/architecture/ssh-conventions.md`.
- **Long-running-job pattern** (Stage 02) — never hold an SSH connection
  open for a CFD/training run. Submit with `scripts/run_long.sh <alias>
  <session> <command>` (detached `tmux`, returns immediately), then poll via
  `run_long.sh status|wait|logs`. Sentinels: `.done` / `.failed`.
- **aero LXC fleet** (Stage 02, +Stage 04) — LXCs 210-217 are the aero
  platform's own (217 `aero-vault` added in Stage 04). **Do not touch any
  other LXC/VM**: the non-aero guests (101-114, 200-207, VMs
  100/104/111/112) are off-limits beyond the explicitly-shared services
  (Postgres 202, Grafana 205, Tempo 204, Redis 203, TrueNAS 104).
  Topology: `docs/architecture/proxmox-topology.md`.
- **Production-tag UQ requirement** — TBD in Stage 12; any
  `tag=production` MLflow run will require a `--uq` envelope.
- **Surrogate certificate-of-validity check** (Stage 08, ADR-008; CONSTITUTION
  Invariant 9) — every surrogate is a subclass of
  `aero.surrogates._common.base:Surrogate` that ships with a typed
  `aero.surrogates._common.certificate:CertificateOfValidity`. Two gates,
  enforced by `CertificateOfValidity.assert_current(current_dataset_hash, now)`:
  (i) **time gate** `now < expires_at` (default lifetime 180 days, ADR-008
  §D5); (ii) **data gate** `current_dataset_hash == training_dataset_dvc_hash`
  (catches dataset drift between expiries). Stage 14's agent layer wraps
  `validate()` in a `try/except CertExpired`; on failure it refuses to
  invoke the model and falls back to a validated solver. The certificate is
  attached to every training run as the MLflow artifact
  `certificates/<surrogate>.json`.
- **Cost cap** — Stage 07 ships the initial $50/month ledger at
  `/etc/aero/runpod-ledger.json`; Stage 13 promotes to the full multi-cloud
  cost router.
- **Self-hosted CI runner** (Stage 03) — `vv-smoke` runs the NACA 0012
  walking-skeleton smoke test on a self-hosted runner labeled `vv`,
  registered on `aero-build`. Not a required status check.
- **OpenFOAM walking skeleton** (Stage 03) — `aero run naca0012 --executor
  local-ssh` drives the end-to-end slice. The OpenFOAM-ESI v2412 SIF is at
  `/opt/aero/containers/openfoam-esi.sif`; solver SIFs run **as the LXC
  root** (`ssh root@aero-build` — non-root `apptainer exec` fails in the
  unprivileged LXC). Cases are written to the shared NFS dataset
  (`/mnt/aero-nfs/runs/` host-side, `/mnt/aero/runs/` inside the LXC).
  Adapter: `aero.adapters.openfoam`; see ADR-003.
- **Four-fold provenance** (Stage 04) — every run logs four MLflow tags
  (`git_sha`, `dvc_input_hash`, `container_sif_sha256`, `config_hash`); the
  CLI fails loud if any cannot be computed (no run is logged with fewer than
  four). The MLflow tracking server is on `aero-mlflow:5000`, backed by
  Postgres LXC 202 (`aero_mlflow` DB) plus a MinIO sidecar. **The Postgres
  `mlflow_artifact_provenance` mirror lives in the shared LXC 202
  (`aero_provenance` DB) — read/writes go through MLflow, never direct.**
  Case configs are composed by Hydra from `conf/`; secrets come from Vault
  on `aero-vault` (LXC 217). `aero run` now requires the live cluster. See
  ADR-004.
- **Solver protocol + SU2 v8 adapter** (Stage 06) — `aero/adapters/_base.py`
  holds the generalised `Solver` ABC (template-method `prepare`, abstract
  `mesh`/`run`/`load`/`wall_distribution` seams) and the structural
  `SolverProtocol` the V&V harness types against. **Every solver's
  `load()` returns a typed `SolveResult` with a typed `ConvergenceHistory`
  — never `xr.Dataset.attrs[...]` (Constitution Invariant 7).**
  `aero/adapters/su2/` is the second concrete solver; `SU2Solver(Solver)`
  consumes both the OpenFOAM TMR specs (so the TMR cases run through
  either solver) and SU2-native specs (`SU2AirfoilSpec`, `SU2MeshFileSpec`).
  `aero[su2]` carries `mpi4py`/`meshio` — independent of `aero[openfoam]`.
  The SU2 SIF is built two-step (rootless-buildah OCI image →
  apptainer-from-oci-archive; the unprivileged-LXC %post sandbox blocks
  sockets, but rootless buildah/podman on the same LXC have slirp4netns
  network access). `containers/su2-v8.{Dockerfile,def}` +
  `scripts/build_su2_sif.sh`. CLI: `aero run --solver {openfoam,su2}` and
  `aero vv run --solver ...`. New CI: `import-platform-only.yml` (the
  PLATFORM-NOT-HUB invariant is now structurally enforced) and
  `vv-transonic.yml` (nightly only, not PR-gating). See ADR-006.
- **GPU solver adapters + cloud cost cap** (Stage 07) — `aero/adapters/pyfr/`
  (`PyFRSolver`, BSD-3, PyFR 1.15.0 in `containers/pyfr.sif`) and
  `aero/adapters/nekrs/` (`NekRSSolver`, BSD-3, NekRS v23.0 in
  `containers/nekrs.sif`) are the platform's third and fourth concrete
  solvers — both GPU-resident, both time-accurate. Their landing forces a
  protocol promotion (ADR-007): **`MeshHandle.n_cells` → `.n_elements`** with
  a sibling `n_dof` for FR/SEM; **`SolveResult.cd`/`.cl` are now
  `float | None`** with a new `scalars: dict[str, float]` for case-specific
  outputs; **`SolveResult.history` is now `ConvergenceHistory | TimeHistory`**
  (Pydantic-discriminated union — Invariant 7 amended to TYPED-SOLVE-HISTORY);
  **`build_apptainer_exec(gpu=True, mpi_n=N)`** appends `--nv` / wraps in
  `mpirun -n N`. Airfoil V&V evaluators `assert result.cd is not None`
  (FAIL-LOUD). `aero[pyfr]` carries `h5py`/`mako`, `aero[nekrs]` carries
  `meshio` — both kept light because the solver binaries live inside the
  SIFs. New `aero[gpu-rental]` extra carries `requests` for the RunPod
  GraphQL transport.

  The minimal **`RunPodExecutor`** (`aero/orchestration/runpod/`) satisfies
  the existing `Executor` protocol: one pod per call, no pool, no router
  (Stage 13 promotes). Every `run()` passes through
  `aero/orchestration/cost_cap.py:CostCap.check_budget()` BEFORE any spend
  — the new **CONSTITUTION Invariant 8 — COST-CAP-ENFORCED-CLOUD-EXECUTION**.
  The ledger is at `/etc/aero/runpod-ledger.json` (mode 0640); default cap
  `$50/month` via `AERO_RUNPOD_MONTHLY_CAP_USD`. Pods terminate in a
  `finally:` block; if termination polling fails the entry is tagged
  `"orphaned"` and all subsequent launches refuse until the operator runs
  `aero cost clear-orphan <run_id> --tag ok|errored`.

  RunPod's container image is the GHCR-mirror of the SIF
  (`ghcr.io/ernesto01louis/aero-{pyfr,nekrs}:<ver>`); the container digest
  also enters `containers/SHA256SUMS` so the four-fold provenance tuple
  resolves whether the run used the local SIF or the pulled image. New CLI:
  `aero run/vv run --executor {local-ssh,runpod} --solver {openfoam,su2,pyfr,
  nekrs}` plus `aero cost {show,clear-orphan}` for ledger inspection. New
  CI workflow `vv-scale-resolving.yml` (nightly, gated on a `[self-hosted,
  gpu]` runner — operator-provisioned). See ADR-007.

- **JAX-Fluids + Surrogate plumbing** (Stage 08, ADR-008) — `aero/adapters/
  jax_fluids/` (`JaxFluidsSolver`, MIT — the stage prompt's GPL-3 assumption
  was incorrect; corrected in ADR-008 §D2) is the platform's **fifth** concrete
  solver and the **first differentiable** one. It uses the standard SIF
  executor lifecycle exactly like every other adapter (same four-fold
  provenance, same cost-cap path); on top, the additive method
  `JaxFluidsSolver.differentiable_run(case, jax_grad_target)` runs in-process
  against `jaxfluids` and bypasses the executor + cost-cap BY DESIGN to
  expose JAX gradients. The Solver ABC is NOT amended (ADR-008 §D3) — a
  second differentiable adapter in Stage 10 or 13 will trigger the
  promotion. The JAX-Fluids version pin is **`JAX-Fluids-v0.2.1`** (latest
  2.x-generation tag at session start; upstream tags the second-generation
  rewrite `v0.2.x` despite the literature calling it "2.0"). Install path is
  git+url — JAX-Fluids is not on PyPI. New extras: `aero[jax-fluids]`
  (h5py + jax + jaxlib + jaxfluids from git+url) and `aero[surrogate-smoke]`
  (torch + torch-geometric + einops + mlflow). Two new SIFs:
  `jax-fluids.sif` (JAX-only) and `surrogate-smoke.sif` (Torch + PyG, no
  JAX) — torch and jax are NEVER in the same SIF (ADR-008 guardrail).

  The surrogate plumbing lands the **`Surrogate` protocol** + the typed
  **`CertificateOfValidity`** framework + the dataset loaders. The protocol
  lives at `aero.surrogates._common.base:Surrogate` (ABC + structural
  `SurrogateProtocol`); the cert at
  `aero.surrogates._common.certificate:CertificateOfValidity` with the
  ApplicabilityEnvelope / MetricQuantiles sub-models and the 180-day default
  expiry policy (ADR-008 §D5). The `Sample` / `TaintedSample` Pydantic
  discriminated union propagates the CC-BY-NC taint from loaders into any
  cert the surrogate issues. Three Stage-08 smoke baselines —
  `MLPBaseline`, `FNOSmoke`, `MGNSmoke` — exercise the protocol end-to-end
  on RunPod via the existing `RunPodExecutor` + `CostCap` plumbing
  (CONSTITUTION Invariant 8 still applies). All three ship with
  `cert_status="smoke"` and are explicitly NOT for publication.

  The global GNN library choice is **PyG / torch-geometric** (ADR-008 §D6;
  aligns with PhysicsNeMo's PyG migration and propagates to Stages 09 + 10).
  The DrivAerNet++ CC-BY-NC quarantine is three layers (ADR-008 §D4):
  (i) **structural separator** at
  `aero/surrogates/_common/loaders/non_commercial/`, enforced by the
  `non-commercial-fence.yml` CI workflow that asserts every import of that
  subpackage either produces `non_commercial=True` or carries the
  `# non-commercial: justified` pragma; (ii) **constructor guard**
  (`LicenseAcknowledgmentRequired` raises without
  `acknowledge_noncommercial=True`); (iii) **tainted-sample union**
  propagating into the issued cert. All four public datasets (AhmedML,
  WindsorML, DrivAerML CC-BY-SA + DrivAerNet++ CC-BY-NC) are landed via
  DVC; per-dataset `reference.md` carries citation + mirror procedure +
  capacity guidance; `dvc.yaml` stages drive `ingest-{ahmedml,windsorml,
  drivaerml,drivaernet-plus-plus}`. New CLI: `aero surrogate train
  --baseline {mlp_baseline,fno_smoke,mgn_smoke} --executor {local-ssh,runpod}`
  computes the four-fold tuple, calls `fit()`, calls `set_certificate()`,
  composes `SurrogateProvenanceTags` (the four-tuple + five
  surrogate-specific tags), logs all eight to MLflow, and writes the cert
  JSON as the `certificates/<baseline>.json` MLflow artifact. The runpod
  surrogate-training path is plumbed but defers the on-pod training script
  to Stage 09. **CONSTITUTION Invariant 9 added** — no agent invocation may
  bypass `Surrogate.certificate().assert_current()` before `predict()`. See
  ADR-008.

- **V&V harness** (Stage 05) — `aero/vv/` runs canonical NASA TMR cases
  through any `SolverLike` solver, compares against reference data with tight
  tolerances (Cd 3 %, Cf 5 %, Cp 3 %), and logs a `BenchmarkResult` with a
  `validation_tag` MLflow tag. `aero vv list|run|report`; `aero vv run --case
  X --mesh-sweep` runs an ASME V&V 20 GCI study. **Before any
  `production`-tagged run, verify `aero vv report --latest` shows all green —
  a red V&V dashboard means no `production` runs.** A tolerance is a contract:
  a failing case is investigated, never relaxed to pass. The airfoil mesh is
  now an eight-block C-grid (`farfield_extent_chords`, wake cut, y+ < 1 with
  `nutLowReWallFunction`) — the Stage-03 O-grid is retired. `vv-required` is a
  stage-gated required CI check. See ADR-005.

- **DoMINO production surrogate** (Stage 09, ADR-010/011/012) —
  `aero/surrogates/domino/` is the platform's first production surrogate.
  `DominoSurrogate(Surrogate)` (`model.py`) wraps NVIDIA PhysicsNeMo's DoMINO;
  the SIF wraps the NGC container `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08`
  (pinned in `containers/physicsnemo.def`; extra `aero[physicsnemo-cu12]` = PyG +
  warp-lang). The GPU work is behind a **swappable `DominoEngine`** (default
  `PhysicsNeMoDominoEngine`, lazy-imported, cluster-gated); host-side tests inject
  a fake engine. `fit` consumes the loader's `Sample` stream for the
  split/ids/targets/taint; the surface meshes are read by `case_id` from the
  DVC-pulled `cases_root` (`predict(features)` takes the flattened DoMINO surface
  input). `train_domino` (`training.py`) runs the no-PC baseline then the
  **Predictor-Corrector** recipe and logs the observed speedup. The
  **smoke→validated** cert upgrade is gated SOLELY on held-out **Cd MAE p95 < 5%**
  (`promote_to_validated`); `_build_certificate` always returns `"smoke"`.
  **Surrogate validation (Invariant 9, held-out DrivAerML) is de-conflated from
  solver V&V (Invariant 5, NASA-TMR dashboard)** — a DoMINO `"validated"` cert
  does NOT need a green TMR dashboard; only the `"production"` tier does (ADR-010).
  Falsifiable evidence = the `surrogate_vv` artifact
  (`aero/vv/surrogate/compare_surrogate_cfd.py`; CLI `aero vv surrogate`).
  Training runs on the pod via `scripts/stage09_domino_train.py`, submitted by
  `aero surrogate train --baseline domino --executor runpod` (cost-cap gated —
  a full DrivAerML train exceeds the $50/mo cap; operator-approved per-run).
  **Pluggable DVC-remote storage** (ADR-011): `conf/storage/{cloud,nas,minio}` +
  the `aero-cloud`/`aero-nas` remotes in `.dvc/config` flip cloud-now →
  on-prem-NAS-later by config only; the NAS migration runbook is
  `docs/runbooks/stage-09-nas-parallel-cutover.md` (preserves 192.168.2.100).
  **Non-interactive SIF signing** (ADR-012): `scripts/_apptainer_sign.sh` feeds a
  Vault-rendered passphrase, fixing the over-SSH signing failure (nekrs/jax-fluids/
  surrogate-smoke re-signed); the signing key migrates into Vault, the escrow
  rides the NAS ZFS send.

## Pointers (do not re-derive — read these)

- `CONSTITUTION.md` — invariants in spec-kit form
- `CONTRIBUTING.md` — commit conventions and PR workflow
- `pyproject.toml` — optional extras structure (Stages 02–15 add to extras
  here, never to base deps)
- `.claude/rules/conventional-commits.md` — commit format details
- `.claude/rules/handoff-discipline.md` — handoff template usage
- `.claude/rules/fail-loud-pydantic.md` — strict pydantic configuration
  patterns
- `docs/handoffs/_template.md` — the canonical post-stage handoff template
- `docs/adrs/_template.md` — ADR template (MADR-style)
- `scripts/check_handoff_exists.sh` — Stop-hook gate; refuses to allow
  session Stop until the current stage's handoff exists with valid
  frontmatter

## When in doubt

1. Out-of-scope domain need → wrong layer; check the stage prompt first.
2. Generalizable need not in the brief → STOP, propose ADR before code.
3. Cannot be tested → redesign until it can.
4. Re-read this file before adding something that's already covered.
5. Re-read the previous handoff before assuming what exists.

---

*Stage 01 (2026-05-17). Updated by each stage's post-stage handoff write.*
