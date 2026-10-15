# CLAUDE.md — aero-research-platform

> Auto-loaded by Claude Code at session start. This file is the **first
> layer** of the four-layer memory model (CLAUDE.md → `.claude/rules/<topic>.md`
> → `STAGE-NN-*.md` → `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`). Read it,
> then the previous stage's handoff, then the current stage prompt.
> A stale CLAUDE.md misleads every future session — update it whenever
> reality diverges.

## What this project is

`aero-research-platform` is a **hypothesis-driven aerodynamic shape/topology
optimizer** (ADR-013; governing scope `docs/handoff-bundle/00-MISSION-AND-SCOPE.md`).
A researcher brings a hypothesis, plugs in geometry (parametric first; CAD/STL/3MF
later), defines an aerodynamic objective, and the platform returns an **improved,
CFD-verified design** — *topology optimization, but for aerodynamics*, with **CFD as
the ground truth**. The deliverable is the optimizer; the forward CFD + UQ + provenance
stack is the **foundation that makes claimed improvements trustworthy**, not the product.

- **Flapping-wing aerodynamics is the single flagship demonstration domain** (broad +
  underexplored; Re ≈ 10²–10⁴, LEV-dominated, rigid → flexible/FSI). The optimizer is
  demonstrated here.
- **Stance:** general architecture (the `Solver`/`Surrogate` protocols + capability
  layers stay mission-agnostic) + **mission-first prioritization** (effort goes to the
  optimizer + flapping). The **SCOPE-GATE** rule gates *effort allocation, not interface
  generality*.
- **Cut / demoted (ADR-013):** the automotive surrogate zoo (DoMINO/Transolver/FIGConvNet/
  X-MGN on DrivAerML) + MoE; DPW-7/HLPW-5 (NASA TMR kept); the NeMo agent layer +
  literature miner (deferred indefinitely). **Riblets are one example, not a flagship**;
  **PyFR/NekRS/SU2/JAX-Fluids are frozen-optional** (kept, not deleted — SU2 is the
  post-v0.1.0 adjoint seed).

The platform is built session-by-session against a staged plan of **21 stages** (20 per
ADR-013; the Stage-16 certification insertion made it 21 — operator-ratified 2026-07-15), one
Claude Code session per stage (the re-aimed Stage 10–20 map is in
`docs/handoff-bundle/README-handoff.md`). The current stage is named in `.aero-stage` at
the repo root.

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
5. **GPL-3.0-compatible only.** Every locked dependency carries a licence on the ADR-048
   GPL-3.0-compatible allowlist, or a reviewed exact-version exception. This is checked over
   `uv.lock` by `dependency licence scan — Invariant 5`. The base install and the supported
   extras are proprietary-free; NVIDIA CUDA components appear only in the frozen GPU extras.

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
10. **POST-STAGE HANDOFF MANDATORY.** No `v0.0.NN` stage tag or `vX.Y.Z` release tag without
    the matching `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md` with valid frontmatter.
    The `Stop` hook in `.claude/settings.json` enforces this in-session. CI enforces it on tag
    push: `tag-handoff-gate.yml` (Stage 18) runs `scripts/check_release_tag.sh` (ADR-049), and a
    release tag also needs `status: complete`, a resolvable `git_sha_end` with the tagged code tree,
    agreeing versions and the next stage's prompt.
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

### Mission rules added at the optimizer refocus (ADR-013; Stage 09)

12. **IMPROVEMENT-EXCEEDS-UNCERTAINTY.** No reported effect or claimed improvement is
    thesis-grade unless its **CFD-verified delta exceeds k·U95** (k ≥ 1, default 2).
    `U95 = RSS(u95_numerical, u95_statistical, u95_input)` — GCI/ASME V&V 20 covers
    *only* `u95_numerical`; unsteady quantities also need `u95_statistical` (batch-means
    / autocorrelation effective-sample-size after a periodic-steady-state check).
    Optimization **deltas** run baseline + candidate at matched numerics/mesh so
    correlated errors cancel. **Promoted to CONSTITUTION Invariant 10** (ADR-015, ratified
    2026-07-05 at Stage 12; required check `small-signal-gate — Invariant 10`; schema
    `aero/vv/reportable.py`).
13. **NO-SURROGATE-ON-FOREIGN-DATA.** Surrogates train only on the platform's own
    validated CFD; foreign datasets (automotive/aircraft) cannot produce a
    `validated`/`production` certificate (`smoke` exempt). **Promoted to CONSTITUTION
    Invariant 11** (ADR-015, ratified 2026-07-05 at Stage 12; required check
    `data-origin-fence — Invariant 11`; reuses the Stage-08 taint machinery).
14. **CFD-VERIFIED-OPTIMUM-ONLY.** Every reported optimum is verified by ground-truth CFD
    before it is reported; no optimum is claimed on a surrogate prediction alone;
    best-of-N reporting is selection-bias-aware (held-out CFD verification). Guards the
    documented AI-scientist failure modes (Luo et al., arXiv:2509.08713). Pairs with
    Invariants 9 + 10; **promoted to CONSTITUTION Invariant 12** (ADR-027, ratified
    2026-07-15).
15. **VALIDATE-AGAINST-EXPERIMENT.** Forward capabilities validate against
    experimental/DNS reference data (the flapping ladder — `.claude/rules/flapping-
    validation-ladder.md`), not CFD-vs-CFD alone. Every physics-capability stage carries
    ≥1 experiment-anchored gate.
16. **RESULTS-MUST-TRAVEL.** Every exported result is a self-describing bundle
    (`CaseSpec` + four-tuple + U95 envelope + validity context) usable in a thesis
    without the cluster. **Promoted to CONSTITUTION Invariant 13** (ADR-047, ratified by the
    Stage-21 constitution PR). It is delivered as the `aero-result-crate` format v1 (`aero/crate/`,
    `crates/`), with the required `crate round-trip — Invariant 13` CI; it moved from Stage 20 by
    ADR-046 S1.
17. **SCOPE-GATE.** New solvers/ML/agents/features stay deferred unless they directly
    serve the optimizer mission or the flapping-wing flagship. This gates **effort
    allocation, NOT interface generality** — the `Solver`/`Surrogate` protocols stay
    general.

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
- **Production-tag UQ + improvement-exceeds-uncertainty** — reframed by ADR-013
  (Hard Rule 12). The UQ core lands **Stage 12**: total `U95 = RSS(numerical GCI,
  statistical batch-means, input)`; any `tag=production` or `validation_tag=thesis-grade`
  run requires the U95 envelope, and any reported improvement's CFD-verified delta must
  exceed k·U95 (default k=2). Schema skeleton `aero/vv/reportable.py` lands Stage 10.
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
  `certificates/<surrogate>.json`. **Per ADR-013, the agent layer (old Stage 14) is
  deferred indefinitely; the cert gate now guards the optimizer's surrogate-accelerated
  loop (Stage 16) — every surrogate-predicted optimum is re-verified by ground-truth CFD
  (Hard Rule 14).**
- **Cost cap** — Stage 07 ships the cloud-GPU ledger at `/etc/aero/runpod-ledger.json`;
  the default cap is **$150/month** (ADR-014, raised from the initial $50; bumped in
  `aero/orchestration/cost_cap.py` at Stage 10). Sustained ($200–600) and burst ($1–2k)
  tiers are per-campaign-approved. The multi-cloud router (old Stage 13) is deferred; the
  tiers carry over when it lands.
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
  a red V&V dashboard means no `production` runs.** Run the *command*; there is
  no dashboard file to read. `docs/vv-dashboard.html` is a CI build artifact
  (uploaded by `vv-smoke` / `vv-transonic`) and is gitignored — a copy was
  tracked until Stage 19 and had gone 69 days stale, wrong in both directions.
  Since Stage 19 the report is **registry-driven**: a registered case with no
  run at all reports `missing`, renders red, and denies ALL GREEN. Before that,
  rows came only from what MLflow returned, so a case that went red and then
  stopped being re-run vanished from the report entirely and the gate could go
  green by attrition. A tolerance is a contract: a failing case is investigated,
  never relaxed to pass. The airfoil mesh is
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

- **Anti-surrogate-exploitation stack** (Stage 14 inter-stage, ADR-025; reconciled
  to main at Stage-17 open) — four
  pure stdlib+numpy+pydantic modules in `aero/surrogates/_common/`, consumed by the
  Stage-17 surrogate-in-the-loop optimizer (renumbered from 16 by the ratified
  21-stage map): `ensemble.py` (`EnsembleSurrogate`, N≥2
  members of any `Surrogate`, per-member seeds, mean/ddof-1 spread), `calibration.py`
  (held-out ±k·std coverage evidence; refuses collapsed ensembles), `trust_region.py`
  (stateless ratio-test policy on the CFD-verified outcome; `reject-floor` ⇒
  `surrogate_distrusted` ⇒ route to infill), `infill.py` (Gaussian EI + reserved
  explore-fraction routing; refuses all-zero-std batches). The predict path was
  extended **additively**: `Surrogate.predict_with_uncertainty` default returns
  `SurrogatePrediction(basis="none", epistemic_std=None)` — honest absence, never a
  fabricated zero; `SurrogateProtocol` is untouched (new
  `UncertaintyAwareSurrogateProtocol` instead). `CertificateOfValidity` gained two
  OPTIONAL fields (`ensemble_size`, `uncertainty_calibration`) — pre-ADR-025 cert
  artifacts parse unchanged. The surrogate-stage DRAFT prompt was ratified-with-
  amendments against the committed STAGE-17 prompt at Stage-17 open and the DRAFT
  file dropped in the reconciliation merge (clause dispositions: ADR-031). Audit
  disposition table: `docs/review/2026-07-audit-reconciliation.md`.

- **Optimizer-mission refocus** (Stage 09 close-out, ADR-013/014/016; governing scope
  `docs/handoff-bundle/00-MISSION-AND-SCOPE.md`) — the platform is an **aerodynamic
  shape optimizer**; flapping-wing is the single flagship; the optimization loop is the
  mission (a named milestone, Stage 15 = the thesis checkpoint), not backlog. **Cuts
  (ADR-013):** automotive surrogate zoo (DoMINO-on-DrivAerML as designed),
  Transolver/FIGConvNet/X-MGN, MoE, DPW-7/HLPW-5 (NASA TMR kept), NeMo agent + literature
  miner (deferred indefinitely), riblet/channel-DNS stages (riblets demote to an
  example). **Frozen-optional (kept, NOT deleted):** SU2 (adjoint seed for the
  post-v0.1.0 topology layer), PyFR, NekRS, JAX-Fluids — their adapters, SIFs, tests
  stay; do not invest. **Stage-09 Phase-3 DoMINO training is CANCELLED** ($67–191 avoided)
  — `aero/surrogates/domino/`, `scripts/stage09_domino_train.py`, `physicsnemo.sif`, and
  the **484-run / ~353 GiB DrivAerML** on the `aero-nfs` remote are **frozen in place**.
  **Do NOT delete or touch DrivAerML / `physicsnemo.sif` / `SHA256SUMS` entries without
  literal `approved`** — disk reclaim (~369 GB free on TrueNAS) is a separate
  propose-first decision (ledgered). The re-aimed Stage 10–20 map + cross-stage
  guardrails are in `docs/handoff-bundle/README-handoff.md`. Stage prompts are
  **committed** from Stage 10 on (`docs/handoff-bundle/STAGE-NN-<slug>.md`); each handoff
  authors the next stage's prompt.

- **Arbitrary-geometry ingestion + robust meshing** (Stage 18, ADR-033/034) —
  `aero/geometry/` is the pure stdlib+numpy+pydantic ingestion core: STL (binary+ASCII)
  + single-mesh 3MF loaders with **exact-weld normalization** (bitwise dedup only —
  tolerance merging is a *declared repair*), a typed `QualityReport` (watertightness,
  edge-manifoldness, winding consistency, duplicates, degenerates, pairwise
  self-intersection via sweep-and-prune + Möller), **bounded declared repair** with a
  typed `RepairAction` ledger, and `ingest()` raising fail-loud `GeometryError` (CLI
  `aero geometry ingest`, exit code 5). STEP rides behind the **`aero[cad]` extra**
  (`build123d==0.11.1`, Apache-2.0 atop OCP/OCCT LGPL-2.1+exception — disposition in
  ADR-033); `load_step` lazy-imports and exact-welds OCCT's per-face tessellation.
  `import-platform-only` imports `aero.geometry` and bans the CAD kernels.

  The mesh side (`aero/adapters/openfoam/`): `mesh_quality.py` is the typed checkMesh
  gate (M1 "Mesh OK", M2 non-ortho ≤ 65, M3 skew ≤ 4, M4 no negative volumes, M5 ≥ 1000
  cells — missing metrics FAIL, never pass); `external_geometry.py` writes quasi-2D
  snappy cases (**one-cell slab at target resolution, castellate+snap with NO volumetric
  refinement** — snappy cannot refine anisotropically — then `flattenMesh` + `empty`;
  `exprFixedValue` parabolic inlet, confirmed working in the v2412 SIF, with a
  `timeVaryingMappedFixedValue` fallback); `robust_mesh.py` walks the pre-registered
  fallback ladder (R0 layers → R1 no layers → R2 1.5× coarser) — the ladder degrades
  COST, never thresholds (F4 structural), exhaustion raises `GeometryError` with the
  full `MeshLadderReport`. `OpenFOAMSolver.mesh()` runs external-geometry meshes
  **detached** (snappy exceeds the legacy 900 s sync cap). The spec's `surface_sha256`
  rides in `config_hash`; the writer refuses byte-mismatched surfaces.

  The Turek-Hron cylinder+flag geometry is EXTERNAL: extracted from the pinned
  `precice/tutorials` blockMesh case (LGPL-3.0) with a declared two-cap closure, strict
  gate zero-repair verified — full provenance + published CFD1/2/3 values in
  `data/references/fsi/turek_hron_fsi3/reference.md` (STL DVC-tracked + sha256
  sidecar the V&V cases verify). V&V: `aero/vv/external_geometry/` — `turek_hron_cfd2`
  (gated: cd 5 %, cl 10 %) + `turek_hron_cfd3` (stretch: cd 5 %, f 5 %, amplitude
  15 %; near-zero mean lift is a diagnostic). The `aero vv run` path is single-shot
  (no ladder) — promoting the ladder into the runner is ledgered.

- **Release: result crates, licence scan, release governance** (Stage 21, ADR-046/047/048/049;
  v0.1.0) — Stage 21 was release-first (ADR-046). **The optimizer has never been run on a
  flapping-wing case, and v0.1.0 makes no flapping-wing optimization claim**; Stage 22 is
  rigid-flapping optimization, and flexible flapping is deferred (ADR-046 S4/S5).
  **Result crates** (`aero/crate/`, format v1; CONSTITUTION Invariant 13): every externally
  reported result is an `aero-result-crate` — RO-Crate 1.3 + Process Run Crate 0.6 + PROV-JSON,
  content-addressed config preimages (`sha256(configs/<hash>.json) == config_hash`), and a
  `SHA256SUMS` whose sha256 is the citable **crate digest**. The reader hashes every member before
  parsing and recomputes computed fields bit for bit; `python -I -B -m aero.crate
  verify|show|numbers|pack` runs sandboxed with only stdlib + numpy + pydantic. **Producer
  contract:** keep the exact `resolved_config` passed to `compute_provenance` and call
  `aero.crate.write_crate`; never write a crate under `data/vv/`. Committed crates (`crates/`) are
  immutable and a regression corpus; their digests are pinned in `scripts/crate_oracle.py` (an
  independent stdlib oracle that never imports `aero`), so a new crate updates the oracle in the
  same PR. Format v1 is frozen: any change is v2 plus an ADR. **Licence scan** (Invariant 5,
  ADR-048): `scripts/licence_scan.py check` over `uv.lock`. A lock change that adds or moves a
  package needs `refresh` of `ci/licence/metadata-snapshot.json`, and possibly a reviewed
  exact-version exception in `ci/licence/exceptions.toml`; stale or unused exceptions fail.
  **Release governance** (ADR-049): `scripts/check_release_tag.sh` gates `vX.Y.Z` tags (exactly
  one handoff with that `stage_tag`, `status: complete`, a `git_sha_end` with the tagged code
  tree, the next stage's prompt, agreeing versions), and `scripts/release_readiness.py --gate
  release --online` verifies every required context green (skipped is not green). The version is
  static in pyproject and bumped only in a release PR; pyproject == `aero.__version__` == the
  `uv.lock` root == CITATION.cff. The **12 required contexts** are listed in
  `.github/required-checks.json`, which must equal branch protection (`test_workflow_hygiene.py`).
  **Gotchas:** actions are SHA-pinned and hosted jobs pinned to `ubuntu-24.04`; squash merges
  break stacked branches (merge `main` in and take main's copy of the base's files); commit
  headers must be ≤ 100 characters **before** pushing, since fixing one needs a force-push; numpy
  reductions differ in the last bit across CPUs, so pinned bytes of numpy output need a committed
  snapshot. **JOSS:** only the operator replies to editors and reviewers; an agent never drafts a
  review comment (`docs/release/joss.md`).

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

*Stage 01 (2026-05-17); updated through Stage 21 (2026-10-15, v0.1.0) by each stage's post-stage handoff write.*
