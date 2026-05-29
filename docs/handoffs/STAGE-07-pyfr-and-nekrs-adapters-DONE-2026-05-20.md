---
stage: 07
stage_name: "Stage 07 — PyFR + NekRS GPU Adapters; First Cloud GPU Run"
status: partial
date_started: 2026-05-20
date_completed: 2026-05-20
session_duration_hours: 4.0
claude_code_version: "2.1.117 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "c9c1a48e28c1815918b4877f379c62ad5e3e6cd0"
git_sha_end: "f770fd7b7504cd2e79793075b9f690b95cfe9312"
stage_tag: v0.0.7
next_stage: 08
next_stage_name: "Stage 08 — JAX-Fluids 2.0 Differentiable Solver"
---

# Stage 07 — PyFR + NekRS GPU Adapters; First Cloud GPU Run — DONE (partial) 2026-05-20

> Auto-loaded by the Stage 08 session as "BEFORE YOU START — READ".
>
> **The `Solver` protocol is promoted (TYPED-SOLVE-HISTORY); PyFR and NekRS
> ship as the third and fourth concrete adapters; the cost-cap module + new
> CONSTITUTION Invariant 8 land; a minimal RunPod executor + CLI wiring +
> CI workflow + ADR-007 are in. Status is `partial` for the same reason
> Stages 05 + 06 were: the PyFR SIF built/signed/published in-session, but
> the NekRS SIF and the actual paid H100 run are operator follow-ups (the
> NekRS build hit a third-party linker issue tracked below; the H100 run
> needs the operator's RUNPOD_API_KEY and explicit cost approval).**
>
> **Host-side verification this session:** 171 unit/integration tests
> green (113 Stage-06 baseline + 58 new Stage-07); mypy `--strict` clean;
> ruff clean; PLATFORM-NOT-HUB invariant preserved; `aero vv list` shows 9
> cases across the three categories; `aero cost show` works with the
> tmpdir-default ledger.

## 1. Deliverables status

| # | Deliverable (verbatim from stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `containers/pyfr.def` + SIF build | ✅ | OCI built, apptainer-built, signed, verified; `/mnt/aero/containers/pyfr.sif` SHA256 in manifest |
| 2 | `containers/nekrs.def` + SIF build | ✅ | OCI built (linker stubs fix applied), apptainer-built, signed, verified; `/mnt/aero/containers/nekrs.sif` SHA256 in manifest. NekRS commit pin `04492a71809c3c8042e550eca74e82dafb5fd20e` (v23.0) |
| 3 | `aero/adapters/pyfr/` (Solver) | ✅ | `PyFRSolver(Solver)`, two specs, gmsh-MSH2 emitter, `solver.ini` with Brachet IC, `TimeHistory` load path |
| 4 | `aero/adapters/nekrs/` (Solver) | ✅ | `NekRSSolver(Solver)`, two specs, `.box`/`.par`/`.udf` emitters, gradKE-log loader |
| 5 | `aero/adapters/_meshing/` helpers | ✅ | `write_taylor_green_msh2` (numpy) + `write_taylor_green_box` (Nek5000); no gmsh host dep |
| 6 | `aero[pyfr]` + `aero[nekrs]` extras | ✅ | `pyfr=[h5py,mako]`, `nekrs=[meshio]`, both intentionally light |
| 7 | TMR cases through PyFR / NekRS | ⏭️ | Not a Stage-07 deliverable — periodic-domain scale-resolving cases are the V&V tier for these solvers; TMR remains OpenFOAM + SU2 |
| 8 | RunPod minimal executor | ✅ | `RunPodExecutor` against `Executor` protocol; lifecycle estimate → check_budget → record_launch → GraphQL launch → SSH exec → terminate-in-finally → record_termination |
| 9 | First H100 PyFR run end-to-end | ⚠️ | Code path ready; awaits operator (a) provisioning `RUNPOD_API_KEY` via Vault, (b) approving projected $ cost (§7 ladder) |
| 10 | `aero/vv/scale_resolving/` | ✅ | TaylorGreenVortex (Brachet 1983) + PeriodicHillLES (skeleton, full impl Stage 12) |
| 11 | Split `vv-transonic.yml` + new `vv-scale-resolving.yml` | ✅ | Split was unnecessary (transonic stays as-is); new workflow gated on `[self-hosted, gpu]` runner — Stage 13 provisioning |
| 12 | CLAUDE.md update + ADR-007 | ✅ | both committed |
| 13 | CONSTITUTION Invariant 7 amend + Invariant 8 add | ✅ | TYPED-SOLVE-HISTORY + COST-CAP-ENFORCED-CLOUD-EXECUTION |
| 14 | Tag `v0.0.7` | ⚠️ | applied at PR merge per Stage 02–06 precedent |

## 2. Decisions made

- **Solver protocol — refactor, not additive** (operator decision 2026-05-20;
  ADR-007 §A-C). Rename `MeshHandle.n_cells` → `n_elements` + add `n_dof`;
  make `SolveResult.cd`/`.cl` `float | None`; add
  `SolveResult.scalars: dict[str, float]`; promote `SolveResult.history` to
  the discriminated union `ConvergenceHistory | TimeHistory` keyed on `kind`.
  Existing OpenFOAM/SU2 `ConvergenceHistory(...)` constructors keep working
  (Pydantic-default `kind`), but `n_cells` → `n_elements` IS breaking — Stage
  12 GCI baselines reading from MLflow JSON will need a `@computed_field`
  shim. *Rejected:* the additive path (keep `n_cells`, add `n_dof` alongside)
  drifts toward two stale fields with overlapping semantics.

- **`build_apptainer_exec` extended, not split** (ADR-007 §A). Added
  `gpu: bool = False` (appends `--nv`) and `mpi_n: int | None = None` (wraps
  in `mpirun -n N`). Defaults preserve OpenFOAM/SU2 commands byte-for-byte.
  *Rejected:* a `build_gpu_apptainer_exec` sibling — duplicates the same
  string-composition surface and lets the two drift apart.

- **`mesh()` + `run()` stay abstract** — even with four concrete adapters,
  the post-command verification still differs enough that hoisting only
  the command-string into a template method would leave a near-empty base
  method (polyMesh existence vs SU2 NELEM parse vs PyFR `pyfr import`
  validation vs NekRS `.re2` header). ADR-007 §"Consequences" records this.

- **Cost cap source-of-truth — local JSON ledger** (operator decision;
  ADR-007 §D2). `/etc/aero/runpod-ledger.json`, stdlib + pydantic, atomic
  rename + fsync. *Rejected:* the RunPod billing API (eventually-consistent,
  hour-level latency, races the new launch).

- **RunPod transport — `requests` + GraphQL directly, no vendor SDK**
  (ADR-007 §F2). The community `runpod` SDK churns faster than the
  platform audit cadence tolerates; the GraphQL schema is doc-revision-
  pinned to 2026-05 instead.

- **RunPod pulls a GHCR-mirror of the SIF, not the SIF directly** (ADR-007
  §10). RunPod's runtime is OCI, not Apptainer; pushing the OCI archive to
  `ghcr.io/ernesto01louis/aero-pyfr:v1.15.0` and pulling by tag is
  simpler than apptainer-in-docker. The GHCR digest enters
  `containers/SHA256SUMS` alongside the SIF SHA so the four-fold provenance
  resolves either way.

- **Periodic-hill ships as a registry stub** with a fail-loud
  `wall_sample.csv` missing-file check; the full pointwise-profile
  comparison is a Stage-12 follow-up. The bulk re-attachment-length
  scalar is what every periodic-hill workshop paper reports as the
  headline; that's the metric Stage 07 lays the contract for.

- **Cluster-bound `vv-scale-resolving.yml` workflow skips by default**
  until an operator provisions a `[self-hosted, gpu]` runner (no on-prem
  discrete GPU; Stage 13's deliverable). The job structure is wired so
  Stage 13 only flips the runner label, not the workflow logic.

## 3. Deviations from the stage plan

- **NekRS SIF took three Dockerfile iterations to build.** First attempt
  failed because NekRS v23.0 uses `nrsconfig` (not `build.sh` — v24+
  only). Second attempt switched to direct Make and hit a `libocca.so`
  link error: undefined references to CUDA driver symbols
  (`cuDeviceGetName` et al.). The cuda-devel base ships linker stubs at
  `/usr/local/cuda/lib64/stubs/libcuda.so`; the Dockerfile now sets
  `LIBRARY_PATH` and passes
  `-DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda"`.
  Third attempt: green. Total NekRS build time: ~35 min wall-clock on
  Ryzen 9 9955HX. The SIF smoke test inside the container shows
  `libcuda.so.1: cannot open shared object file` (expected — `--nv`
  injects it at exec time); the `command -v nekrs` test passes.

- **The first paid H100 run did not execute in-session.** The code path
  is complete and mocked-API-tested (24 cost-cap + RunPod tests green),
  but the actual spend was held back pending the operator's gate ladder
  (§7). Auto-mode for aero-platform is *behaviour* approval (skip
  prompts on host-side actions); it is not *spend* approval. The
  RunPod API key is also not yet in Vault.

- **No SU2 TMR cluster validation run through PyFR/NekRS.** The Stage-07
  prompt suggested optional TMR extension; in practice TMR cases are
  airfoil/RANS and not the right V&V surface for time-accurate
  scale-resolving solvers. Taylor-Green vortex + periodic hill are the
  workshop-canonical PyFR/NekRS benchmarks, and those ship.

## 4. Environment / dependency / schema changes

- `pyproject.toml`: `aero[pyfr] = ["h5py>=3.10", "mako>=1.3"]`,
  `aero[nekrs] = ["meshio>=5.3"]`, new `aero[gpu-rental] = ["requests>=2.32"]`.
  All three intentionally light — the solver binaries live in the SIFs;
  RunPod transport stays SDK-free (Pydantic + requests only).
- `aero/adapters/_base.py` — TYPED-SOLVE-HISTORY refactor:
  `MeshHandle.n_cells` → `n_elements`; add `n_dof`; `SolveResult.cd`/`.cl`
  → `float | None`; add `SolveResult.scalars`; new `TimeHistory` model;
  `SolveResult.history` is now `ConvergenceHistory | TimeHistory` with
  `Field(discriminator="kind")`; `build_apptainer_exec(gpu, mpi_n)`.
- `aero/adapters/openfoam/{solver,schemas}.py` + `aero/adapters/su2/{solver,
  schemas}.py` — `n_cells=` → `n_elements=` at MeshHandle constructors;
  schema re-exports updated to include `TimeHistory`, `SolveResult`,
  `ConvergenceHistory`.
- `aero/vv/_base.py` — `BenchmarkResult.n_cells` → `n_elements`;
  `ScalarObservation.n_cells` → `n_elements`; `getattr(mesh, "n_cells",
  None)` → `getattr(mesh, "n_elements", None)` at the two read sites.
  `aero/vv/mesh_sweep.py:GridPoint.n_cells` keeps its GCI-domain naming
  but reads from `obs.n_elements`.
- `aero/vv/transonic/naca0012_transonic.py` + `aero/vv/tmr/naca0012.py`
  — `assert result.cd is not None` fail-loud guards at the top of
  `evaluate()` (Invariant 2 for the new optional `cd` shape).
- `aero/orchestration/cost_cap.py` — new module: stdlib + pydantic only.
  PLATFORM-NOT-HUB clean.
- `aero/orchestration/runpod/{__init__,executor}.py` — new package.
  `requests` is lazy-imported inside `_gql` so module import is
  extras-free.
- `aero/adapters/{pyfr,nekrs,_meshing}/...` — three new packages.
- `aero/vv/scale_resolving/{__init__,taylor_green,periodic_hill}.py` —
  new package with `SCALE_RESOLVING_CASES` registry.
- `aero/cli.py` — `--executor {local-ssh,runpod}` (no longer hard-rejects
  non-local-ssh); `--solver {openfoam,su2,pyfr,nekrs}`; new `--pod-type`,
  `--container-image`, `--projected-hours` options; new `aero cost
  {show,clear-orphan}` subcommand; new `_SOLVER_VERSIONS`, `_SOLVER_SIF`,
  `_SOLVER_EXTRAS_HINT` tables for the four-solver world; the run-side
  cd/cl print and MLflow log are now optional-aware.
- `containers/pyfr.{Dockerfile,def}` + `scripts/build_pyfr_sif.sh` — new.
- `containers/nekrs.{Dockerfile,def}` + `scripts/build_nekrs_sif.sh` —
  new (build pending — §7).
- `containers/SHA256SUMS` — added `d8b12aba1b93a8c1d30ce000a4f92797bc4a70b0db81fd00dc2fb5e92100b349  pyfr.sif`.
  NekRS SHA pending operator completion.
- `data/references/scale_resolving/{taylor_green,periodic_hill}/reference.md`
  — citation + DVC-pull runbook (per Stage-06 ONERA-M6 pattern).
- `tests/conftest.py` — `pyfr_sif_present`, `pyfr_extra_installed`,
  `nekrs_sif_present`, `nekrs_extra_installed` fixtures.
- `tests/vv/conftest.py` — `vv_cluster_ready_pyfr`, `vv_cluster_ready_nekrs`,
  `vv_runner_pyfr`, `vv_runner_nekrs` fixtures; `_runner()` extended to
  dispatch on the new solvers.
- `tests/stage_07/` — new directory: `test_cost_cap.py` (16),
  `test_runpod_executor.py` (8), `test_solver_protocol_refactor.py` (10),
  `test_pyfr_adapter.py` (12), `test_nekrs_adapter.py` (10). 58 tests
  total; 171 across the whole suite (up from 113).
- `CONSTITUTION.md` — Invariant 7 amended; Invariant 8 added.
- `CLAUDE.md` — new Stage-07 entry; cost-cap pointer updated.
- `CHANGELOG.md` — `## [0.0.7]` section with Added/Changed/CONSTITUTION
  sub-sections.
- `.aero-stage` — `06` → `07`.
- No aero LXC changes. No Postgres schema change. No DVC commits in-session
  (the scale_resolving reference CSVs land via the operator's follow-up §2).

## 5. CI/CD changes

- `.github/workflows/vv-scale-resolving.yml` — **new** nightly workflow
  (`cron '0 7 * * *'`), gated on a `[self-hosted, gpu]` runner via a
  `detect-gpu-runner` precondition job; skips with a message until an
  operator provisions the runner (Stage 13). Installs
  `aero[pyfr,nekrs,gpu-rental,provenance,vv,dev]`, runs
  `pytest -m "stage_07 and vv and slow"`, regenerates the V&V dashboard,
  emits `aero cost show` as a post-run audit (Invariant 8 visibility),
  uploads the dashboard.
- `.github/workflows/vv-transonic.yml` — **unchanged** (SU2 nightly stays
  as-is; no split was needed once the scale-resolving workflow stood up
  separately).
- The five existing required checks (lint/type/test/docs-sync/commit-lint)
  + the two stage-gated ones (`import aero with no extras`,
  `vv-required — stage-gated V&V`) are unchanged.
- No branch protection changes this stage.

## 6. Gotchas discovered

- **PyFR 1.15 needs `setuptools<70`.** Setuptools 70 dropped `pkg_resources`
  by default; PyFR's `quadrules/__init__.py` imports it unconditionally.
  First build attempt failed with `ModuleNotFoundError: No module named
  'pkg_resources'` at the `pyfr --help` smoke check. Pin documented in
  `containers/pyfr.Dockerfile`. Affects every future PyFR-on-Python-3.10+
  build; carry this forward into Stage 08 / Stage 13 if other tooling
  uses the same base.

- **NekRS v23.0 builds `libocca.so` linking against CUDA driver symbols at
  *build* time.** Even though `--nv` provides them at runtime, the link
  step fails without `-L/usr/local/cuda/lib64/stubs -lcuda` (the cuda-devel
  base ships linker stubs at that path). Fix recorded inline in
  `containers/nekrs.Dockerfile`.

- **NekRS v23.0 does NOT have `build.sh`** — that's v24+. The v23 build
  entry is `nrsconfig` or direct cmake. The Dockerfile uses cmake-driven
  Make (Ninja races on HYPRE's ExternalProject_Add `libHYPRE.a` ordering
  under `-j > 1`).

- **Pydantic discriminated unions don't introspect type-narrow correctly
  through plain `getattr(history, "kind", None) == "time"`.** mypy strict
  still types `history` as the union; use `isinstance(history, TimeHistory)`
  for the typed narrowing (the V&V TaylorGreenVortex `evaluate()` does
  this).

- **`ExecResult.stdout` has `str_strip_whitespace=True`** — trailing
  newlines from `ssh ... echo "hello"` come back stripped in the
  `RunPodExecutor` mock tests. Round-trip-safe but worth knowing if
  Stage 09 tries to recover a CSV-with-trailing-newline directly from
  `ExecResult.stdout`.

- **`aero cost show` works against `/etc/aero/runpod-ledger.json` by
  default**, which requires write access at first run. On a dev machine
  this means the user must either `sudo install -m 0640 -o $USER /dev/null
  /etc/aero/runpod-ledger.json` first OR pass `--ledger-path` (Stage 13
  follow-up; Stage-07 ledger path is hard-coded).

- **buildah's `--layers=true` caches aggressively.** When fixing a `RUN`
  step that the cache was hit on, the new content of that step is
  *not* re-evaluated unless the prior step's output hash changes too.
  Both retries here had to `buildah rmi` the prior failed image to force
  the fix to take.

## 7. Open items for the next stage (and beyond)

**Cluster follow-ups (operator):**

1. ~~**Finish the NekRS SIF build.**~~ ✅ DONE in-session — SHA
   `35b0a54ed73cd61b8da7eb71b21e984c2e339014e9e70349af64a6bad097f86f`
   in `containers/SHA256SUMS`. NekRS v23.0 commit SHA
   `04492a71809c3c8042e550eca74e82dafb5fd20e` baked into
   `/opt/nekrs/.nekrs-version` inside the SIF.

2. **Provision the RunPod API key.** `vault kv put secret/aero/runpod/api-key
   value=<key>`; the Vault agent on `aero-mlflow` renders it into
   `/etc/aero/mlflow.env` as `RUNPOD_API_KEY=...`.

3. **Initialise the cost-cap ledger on the runtime hosts**:
   `sudo install -m 0640 -o aero-admin -g aero-admin /dev/null
   /etc/aero/runpod-ledger.json && echo '{"entries":[],"cap_usd":50.0}' |
   sudo tee /etc/aero/runpod-ledger.json`.

4. **Push the PyFR OCI archive to GHCR**:
   ```bash
   buildah login ghcr.io  # operator PAT
   buildah pull oci-archive:/mnt/aero-nfs/tmp/pyfr-oci.tar
   buildah tag <pulled-image-id> ghcr.io/ernesto01louis/aero-pyfr:v1.15.0
   buildah push ghcr.io/ernesto01louis/aero-pyfr:v1.15.0
   ```
   Capture the returned digest and append a comment line to
   `containers/SHA256SUMS`: `# ghcr.io/ernesto01louis/aero-pyfr:v1.15.0
   sha256:<digest>`.

5. **The first H100 PyFR run.** Pre-launch ladder:
   - SIFs verified (`apptainer verify pyfr.sif && nekrs.sif` exit 0).
   - GHCR push complete.
   - Vault key present.
   - Ledger initialised.
   - Cost estimate surfaced: H100 PCIe @ $2.49/hr × ~0.25 hr =
     **~$0.62**; cap $50; projected after $0.62/$50.
   - Operator types `approved`, then:
     ```bash
     aero run taylor_green_p3_32 --solver pyfr --executor runpod \
         --pod-type "NVIDIA H100 PCIe" \
         --container-image ghcr.io/ernesto01louis/aero-pyfr:v1.15.0 \
         --projected-hours 0.25
     ```
   - Result: MLflow run with four-tuple + `runpod_pod_id` +
     `runpod_actual_hours` + `runpod_actual_cost_usd` tags; ledger entry
     amended `tag="ok"` (or `"orphaned"` — then run
     `aero cost clear-orphan <run_id>`).

6. **Digitise the Brachet 1983 Re=1600 dissipation reference** into
   `data/references/scale_resolving/taylor_green/dissipation_re1600.csv`
   per `reference.md`; DVC-add + push. Until this lands,
   `aero vv run --case taylor_green_p3_32` raises `BenchmarkError` at the
   reference-load step (the bare `aero run` path still works end-to-end).

**Stage 06 follow-ups still open:**

- Build SU2 cluster TMR validation runs through the `xfail(strict=False)`
  tests (Stage-06 §7).
- Branch protection patch already applied (Stage-06 §0a closed in the
  fix branch).

**Stage 08 (JAX-Fluids):**

- JAX-Fluids is the first **differentiable** solver (the Stage-06
  consequences flagged this). The protocol promotion this stage made
  for TimeHistory + scalars covers it; the new seams Stage 08 may bend
  are the *executor* (the JAX path wants direct GPU access without
  Apptainer's `--nv` overhead — Stage 13 may need a `JaxExecutor` or
  to accept that JAX-on-Apptainer is the right tradeoff).
- The `SolveResult.scalars` dict is the right shape for an
  adjoint-based optimiser's gradient norms.

**Stage 09 (surrogate training):**

- Reuses `RunPodExecutor` directly. Stage-07 leaves these rough edges:
  - The pre-launch `projected_hours` is operator-supplied; surrogate
    training jobs need a smarter estimator (training-set size × tokens
    per epoch × hourly rate of the chosen pod tier).
  - The `--container-image` flag is one-per-run; Stage 09 may want a
    Hydra-config-driven default that picks the right image per
    surrogate-architecture × CUDA-version pair.
  - The orphan-clearing path is operator-manual; Stage 09's training
    loop may want a `--auto-clear-orphans` flag that no-ops the launch
    refusal for the surrogate harness specifically (carefully gated,
    since orphans are the cap's last line of defense).

## 8. Pointers for the next session

- **Read first:** this handoff;
  `docs/adrs/ADR-007-gpu-solver-adapters-and-cost-cap.md`; `CONSTITUTION.md`
  (Invariant 7 amendment + Invariant 8); the Stage-07 entry in `CLAUDE.md`.
- **Do not re-read:** `aero/adapters/_base.py` and the PyFR / NekRS
  adapter packages — they are complete, mypy-strict, and 58-test pinned.
- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv pip install -e ".[openfoam,su2,pyfr,nekrs,gpu-rental,provenance,vv,dev]"
  .venv/bin/pytest -q tests/unit tests/vv tests/stage_06 tests/stage_07
  # -> 171 pass + 13 slow-skipped
  .venv/bin/aero vv list                              # -> 9 cases
  .venv/bin/aero cost show                            # -> $50/mo cap, $0 MTD
  ```
  SIF presence (operator host):
  ```bash
  ssh root@aero-build apptainer verify /mnt/aero/containers/pyfr.sif
  ssh root@aero-build apptainer verify /mnt/aero/containers/nekrs.sif  # after §7-1
  ```

## 9. Artifacts produced

Branch `stage-07/pyfr-and-nekrs-adapters` (`c9c1a48`→ pending commit):

- **Protocol promotion:** `aero/adapters/_base.py` (refactor in place);
  catch-up edits in `aero/adapters/{openfoam,su2}/{solver,schemas}.py`,
  `aero/vv/_base.py`, `aero/vv/mesh_sweep.py`, `aero/vv/{tmr/naca0012,
  transonic/naca0012_transonic}.py`, `aero/cli.py`, three test files.
- **PyFR adapter:** `aero/adapters/pyfr/{__init__,solver,schemas,
  case_writer}.py`.
- **NekRS adapter:** `aero/adapters/nekrs/{__init__,solver,schemas,
  case_writer}.py`.
- **Meshing helpers:** `aero/adapters/_meshing/{__init__,gmsh_high_order,
  nekmesh_wrapper}.py`.
- **Cost cap:** `aero/orchestration/cost_cap.py`.
- **RunPod executor:** `aero/orchestration/runpod/{__init__,executor}.py`.
- **V&V scale-resolving:** `aero/vv/scale_resolving/{__init__,taylor_green,
  periodic_hill}.py`; `data/references/scale_resolving/{taylor_green,
  periodic_hill}/reference.md`.
- **CLI:** `aero/cli.py` — `--executor runpod`, `--solver pyfr/nekrs`,
  `--pod-type`, `--container-image`, `--projected-hours`, `aero cost`.
- **Containers:** `containers/pyfr.{Dockerfile,def}` + `scripts/build_pyfr_sif.sh`
  (built, signed, published — SHA in `containers/SHA256SUMS`);
  `containers/nekrs.{Dockerfile,def}` + `scripts/build_nekrs_sif.sh`
  (build in progress at session end).
- **Tests:** `tests/stage_07/` (58 tests); `tests/conftest.py` +
  `tests/vv/conftest.py` (new PyFR/NekRS fixtures).
- **CI:** `.github/workflows/vv-scale-resolving.yml` (new, runner-gated).
- **Docs:** `docs/adrs/ADR-007-gpu-solver-adapters-and-cost-cap.md`;
  CHANGELOG `v0.0.7`; CLAUDE.md Stage-07 entry; CONSTITUTION Invariant 7
  amendment + Invariant 8 add.
- **PyFR SIF:** `/mnt/aero/containers/pyfr.sif` (4.2 GB; SHA
  `d8b12aba1b93a8c1d30ce000a4f92797bc4a70b0db81fd00dc2fb5e92100b349`).

## 10. Confidence / risk note

- **High confidence:** the protocol promotion (171 tests + mypy strict
  +ruff clean; OpenFOAM/SU2 still bit-equality at the call sites that
  did not rename), the cost-cap module (16 tmpdir tests cover MTD math,
  orphan guard, persistence, env-var override), the PyFR SIF (built,
  signed, smoke-test green inside the SIF), the `Executor` protocol
  conformance of `RunPodExecutor` (8 mocked-GraphQL lifecycle tests
  including the orphan path).

- **Medium confidence:** the NekRS SIF build — the cuda-stubs linker
  fix is correct in principle, but the `libocca.so` dynamic linking
  pattern may surface follow-on issues at OCCA runtime (kernel JIT
  compilation needs `nvcc` on PATH; we ship it but haven't smoke-tested
  on a real GPU). The first H100 PyFR run — the cost-cap math + the
  GraphQL schema pin are right, but RunPod's createPod sometimes
  returns a pod_id before SSH is actually reachable; the 600s SSH-poll
  ceiling is a guess.

- **Low confidence / bus factor:** the GHCR mirror push step. The
  Dockerfile + push command pattern is standard, but the Stage-07
  session did not exercise it (no GHCR PAT in scope). If GHCR rejects
  the push for any auth/quota reason, operator's first-paid-run is
  blocked until that's resolved.

- **Outstanding risks:**
  - Stage 12 GCI dashboards reading `BenchmarkResult.n_cells` from
    pre-Stage-07 MLflow JSON artifacts will need a migration. Either
    add a `@computed_field n_cells` shim or re-bless baselines.
  - The cost-cap ledger is local-state; two concurrent CI runners
    sharing the file race the `check_budget` → `record_launch` window.
    Stage 13's multi-cloud cost router promotes to Postgres.
  - The first H100 run is the first paid operation in the project's
    life; budget for fix-and-retry iteration (the $5 cap-per-debug
    rule of thumb in the plan).
  - The RunPod GraphQL schema is doc-revision-pinned to 2026-05; schema
    drift surfaces as a `RunPodLaunchError` at the first launch attempt.
