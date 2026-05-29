# ADR-007 — GPU Solver Adapters (PyFR + NekRS), Solver Protocol Refactor, and Cost-Cap-Enforced Cloud Execution

- **Status:** accepted
- **Date:** 2026-05-20
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent
  (Stage 07)
- **Stage:** 07
- **Supersedes:** the "revisit at the third solver (PyFR, Stage 07)"
  provision in ADR-006 §6 (the third *and fourth* concrete solvers now
  exist; the seams are resolved).

## Context and problem statement

Stage 06 generalised the `Solver` protocol from two data points (OpenFOAM,
SU2) and explicitly flagged five seams it expected the third/fourth solver
to bend: `MeshHandle.n_cells`, `SolveResult.cd`/`cl` required, `Convergence
History` as the only history type, `build_apptainer_exec`'s missing
`--nv`/MPI flags, and `mesh()` as a phase. Stage 07 adds **PyFR**
(high-order flux reconstruction) and **NekRS** (spectral element) as the
third and fourth solvers — both GPU-resident, both time-accurate, both
periodic-domain-friendly, both MPI-launched. This is the third and fourth
data point that forces the abstraction to bend honestly.

Stage 07 also crosses a project-wide threshold: the **first paid cloud GPU
run**. Without a budget control between the operator and the RunPod API,
"all-in-session" all-the-way-through means an uncontrolled spend channel
the project cannot afford. This ADR records four decisions:

1. The shape of the Stage-07 `Solver` protocol promotion (refactor, not
   additive — operator decision 2026-05-20).
2. PyFR + NekRS as the third + fourth solvers, and their version pins.
3. The Stage-07 minimal cloud-GPU executor — a `RunPodExecutor` that
   satisfies the existing `Executor` protocol, deliberately stupid (one
   pod per call, no pool, no router; Stage 13 inherits the cleanup).
4. The local-ledger cost-cap design that becomes the CONSTITUTION
   Invariant 8 (COST-CAP-ENFORCED-CLOUD-EXECUTION).

## Decision drivers

- **Pass-3 anti-premature-abstraction.** The third + fourth concrete
  implementations resolve the abstraction; the JAX-Fluids Stage-08 path
  *does* enter the design (its time-accurate differentiable shape was
  one of the seams flagged in ADR-006 §Consequences).
- **PLATFORM-NOT-HUB (Invariant 1) / HEAVY-DEPS-IN-OPTIONAL-EXTRAS-ONLY
  (Invariant 4).** PyFR / NekRS binaries live inside the SIFs;
  `requests` (the cloud executor's transport) lives in `aero[gpu-rental]`.
- **FAIL-LOUD (Invariant 2).** Cost-cap overruns and orphaned pods raise
  typed exceptions; airfoil V&V evaluators `assert result.cd is not
  None` at the boundary.
- **PROVENANCE-FROM-DAY-ONE (Invariant 3).** The PyFR/NekRS SIF SHA256s
  and the GHCR digest both register in `containers/SHA256SUMS`; every
  RunPod run logs the standard four-tuple plus the new
  `runpod_pod_id` / `runpod_actual_hours` / `runpod_actual_cost_usd`.
- **The cap must hold under failure.** The terminate-API-returns-200-
  while-billing-continues mode (well-attested on Vast.ai and RunPod) is
  the most expensive failure; we mark ledger entries `tag="orphaned"`
  and refuse all subsequent launches until the operator clears them.

## Considered options

### A. Protocol shape — additive vs. refactor

- **A1. Additive `n_dof`, keep `n_cells`.** *Rejected.* Drifts toward two
  fields with overlapping semantics. The FV/FR semantic split rings
  cleaner if `n_cells` becomes `n_elements` outright.
- **A2. Rename `n_cells` → `n_elements` + add `n_dof`** (chosen). FV
  solvers populate `n_elements` only; FR/SEM solvers populate both
  (`n_dof = n_elements * (p+1)**d`).

### B. `SolveResult.cd`/`.cl` required vs. optional

- **B1. Keep required, force fake values for non-airfoil cases.**
  *Rejected.* Surrogate / scale-resolving / heat-transfer cases have no
  honest force coefficient; a fake satisfies the type but corrupts the
  V&V dashboard.
- **B2. Make `Optional[float]`, add a `scalars: dict[str, float]` field
  for case-specific outputs** (chosen). Airfoil V&V cases `assert
  result.cd is not None` at the top of `evaluate()` (FAIL-LOUD).

### C. `SolveResult.history` shape

- **C1. Discriminated union `ConvergenceHistory | TimeHistory`**
  (chosen). Pydantic's `Field(discriminator='kind')` keeps the V&V
  harness reading one typed shape; legacy `ConvergenceHistory(...)`
  constructors keep working via Pydantic-default `kind="convergence"`.
- **C2. Two separate `SolveResult` subclasses.** *Rejected.* Forces
  the harness to dispatch on type at every read site.
- **C3. Stringly-typed `history: Any` with a parallel `history_kind: str`.**
  *Rejected.* Re-introduces the `.attrs` antipattern Invariant 7 was
  added to kill.

### D. Cloud cost control — billing-API vs. local ledger

- **D1. Pre-launch GET on RunPod's billing endpoint.** *Rejected.*
  Eventually-consistent (hour-level latency); races the new launch.
- **D2. Local append-only JSON ledger at `/etc/aero/runpod-ledger.json`**
  (chosen). Stdlib + pydantic, atomic rename + fsync on write, mode
  0640. Pre-launch sums month-to-date; refuses orphaned entries.
- **D3. Postgres-backed ledger in `aero_provenance` LXC 202.** *Rejected.*
  Drags a DB dependency into orchestration core (Invariant 1).

### E. PyFR + NekRS as third + fourth solvers

- **PyFR** (BSD-3). Flux reconstruction, GPU-resident, mixed-element-
  capable, the workshop-canonical high-order LES code. Ships a PyPI
  release; the SIF wraps it on `nvidia/cuda:12.4.1-devel-ubuntu22.04`.
  Version pin: **1.15.0** (the most recent stable release).
- **NekRS** (BSD-3). Spectral element, GPU-resident, hex-dominant, the
  workshop-canonical high-order DNS code derived from Nek5000. The SIF
  source-builds NekRS with OCCA + libParanumal kernels for the
  CUDA backend on sm_80 / sm_89 / sm_90. Version pin: **v23.0**.

### F. Cloud GPU executor scope

- **F1. Full multi-cloud cost router with vendor SDKs.** *Rejected for
  Stage 07.* Stage 13's deliverable. RunPod / Lambda / Vast SDKs churn
  frequently; pinning vendor SDKs against the project audit cadence is
  Stage 13's problem.
- **F2. Minimal `RunPodExecutor` against the existing `Executor` protocol,
  GraphQL via `requests`** (chosen). One pod per call, no pool, no spot-
  eviction handling, no queue. Stage 13 sees what bends.

## Decision

1. **`aero/adapters/_base.py` refactor:** `MeshHandle.n_cells` →
   `n_elements`; add `MeshHandle.n_dof: int | None`; `SolveResult.cd`/
   `.cl` → `float | None`; add `SolveResult.scalars: dict[str, float] =
   {}`; introduce `TimeHistory(kind="time", t, monitor, monitor_name)`;
   `SolveResult.history` becomes `ConvergenceHistory | TimeHistory` with
   `Field(discriminator="kind")`; `ConvergenceHistory` gains
   `kind: Literal["convergence"] = "convergence"`; `build_apptainer_exec`
   gains `gpu: bool = False` (`--nv`) and `mpi_n: int | None = None`
   (wraps in `mpirun -n N`). OpenFOAM + SU2 adapters catch up; numbers
   bit-unchanged. Airfoil V&V cases `assert result.cd is not None` at
   the top of their `evaluate()`.

2. **`aero/adapters/pyfr/`** ships `PyFRSolver(Solver)`, two specs
   (`PyFRTaylorGreenSpec`, `PyFRMeshFileSpec`), a case writer (gmsh
   `.msh2` for the periodic TG cube; PyFR `solver.ini` with the
   analytic Brachet IC), and reuses the Stage-07 `MeshHandle.n_dof`
   field for FR's `n_elements * (p+1)**3` DOF count. `mesh()` runs
   `pyfr import` and optional `pyfr partition`; `run()` calls
   `pyfr run -b cuda` with `gpu=True`; `load()` parses
   `out/integrate.csv` into a `TimeHistory(monitor_name="dissipation_rate")`.

3. **`aero/adapters/nekrs/`** ships `NekRSSolver(Solver)`, two specs
   (`NekRSTaylorGreenSpec`, `NekRSCaseDirSpec`), a case writer (`.box`
   for `genbox`, `.par`, `.udf` with the Brachet IC + a per-step KE
   monitor that emits parsable `gradKE:` log lines). `mesh()` runs
   `genbox` + `genmap` inside the SIF; `run()` calls
   `nekrs --backend CUDA` with `gpu=True, mpi_n=N`; `load()` greps
   `gradKE:` lines from the captured solver log into a `TimeHistory`.

4. **`aero/orchestration/cost_cap.py`** defines `CostCap`, `Ledger`,
   `LedgerEntry`, and the `CostCapError` family. Ledger persisted at
   `/etc/aero/runpod-ledger.json` (mode 0640). Default cap: `$50/month`
   (override via `AERO_RUNPOD_MONTHLY_CAP_USD`). The pre-launch
   `check_budget(estimated_usd)` is the only legal gate for any cloud
   executor (`RunPodExecutor` and the future Lambda / Vast paths).

5. **`aero/orchestration/runpod/executor.py`** ships `RunPodExecutor`
   satisfying the `Executor` Protocol structurally. Lifecycle in
   `run()`: estimate cost → `cost_cap.check_budget()` →
   `cost_cap.record_launch(... tag="running")` → launch pod via
   GraphQL → poll for SSH → exec command → terminate pod in a
   `finally:` → `cost_cap.record_termination(...)`. Terminate
   confirmation polls `getPod(podId)` for `desiredStatus = TERMINATED`
   with a 300s ceiling; on poll failure the entry is tagged
   `"orphaned"` and all subsequent launches are refused.

6. **`aero[pyfr]` extras**: `h5py`, `mako` (host-side decoders for
   PyFR's HDF5 outputs). **`aero[nekrs]` extras**: `meshio`. **New
   `aero[gpu-rental]` extra**: `requests` (the GraphQL transport).

7. **CONSTITUTION Invariant 7** amended: TYPED-CONVERGENCE-HISTORY
   → **TYPED-SOLVE-HISTORY** (now covers both the steady-state and the
   time-accurate branches). **CONSTITUTION Invariant 8** added:
   **COST-CAP-ENFORCED-CLOUD-EXECUTION** (every rented-GPU launch passes
   through `CostCap.check_budget()`).

8. **CLI:** `aero run --executor {local-ssh,runpod} --solver
   {openfoam,su2,pyfr,nekrs}` and `aero vv run` accept the same flags.
   New `aero cost {show,clear-orphan}` subcommand for ledger
   inspection.

9. **CI:** new `.github/workflows/vv-scale-resolving.yml` (nightly,
   self-hosted `gpu` runner, gated on the runner existing — Stage 13's
   provisioning). The existing `vv-transonic.yml` is unchanged.

10. **PyFR + NekRS SIFs are built two-step (ADR-006 §C pattern).**
    `buildah` on the Proxmox host runs the source build with network
    access (the `aero-build` LXC %post sandbox blocks sockets); the
    SIF then bootstraps from an OCI archive on the shared NFS dataset,
    apptainer-built + signed on `aero-build`. The OCI archive also
    pushes to GHCR (`ghcr.io/ernesto01louis/aero-pyfr:v1.15.0`,
    `aero-nekrs:v23.0`) as the RunPod-pullable container image — the
    container digest joins `containers/SHA256SUMS` alongside the SIF.

## Consequences

### Positive

- Four-solver platform with a coherent `Solver` protocol; the surrogate
  layer (Stage 09) and the agentic layer (Stage 14) type against one
  shape regardless of whether they wrap a FV, FR, SEM, or differentiable
  solver.
- Time-accurate solves enter the typed result schema; the V&V dashboard
  reads `TimeHistory` without a per-solver special case.
- Cloud GPU path is proven end-to-end; Stage 09 surrogate training reuses
  `RunPodExecutor` without re-design.
- Cost cap is dependency-free, tested with a tmpdir ledger, and fails
  loud on every overrun mode the field has encountered.
- `import-platform-only` stays green (`aero/orchestration/cost_cap.py`
  is stdlib + pydantic only; `aero/orchestration/runpod/executor.py`
  imports `requests` lazily, behind the `gpu-rental` extra).

### Negative / known limitations

- **Refactor breaks Stage-12 GCI baselines** that read `BenchmarkResult.n_cells`
  from MLflow JSON artifacts: Stage 12 will need a `@computed_field
  n_cells -> n_elements` shim, or to re-bless its baselines.
- **Cost cap is local-state, not distributed.** Two concurrent CI runners
  using the same ledger file could race the `check_budget` → `record_launch`
  window. Stage 13's multi-cloud router promotes the ledger to Postgres if
  this becomes real.
- **Periodic-hill `wall_distribution` is deferred to Stage 12.** Stage 07
  ships the case skeleton + the bulk re-attachment-length comparison;
  full pointwise mean-velocity profiles need a host-side sampler that
  parses PyFR's `[soln-plugin-sampler]` output.
- **The cluster-bound `vv-scale-resolving.yml` workflow is skip-by-default
  until an operator provisions a `[self-hosted, gpu]` runner.** Stage 13
  delivers the multi-cloud runner pool; Stage 07 has no on-prem discrete
  GPU.
- **The RunPod GraphQL schema is doc-revision-pinned to 2026-05.** Schema
  drift surfaces as a `RunPodLaunchError` at launch time, not silently.

## Open questions / future work

- Promote the cost-cap ledger to a Postgres-backed implementation in
  Stage 13 (concurrent-CI safety).
- Add `LambdaLabsExecutor` and `VastAIExecutor` against the same `Executor`
  Protocol in Stage 13; the cost-cap module is already vendor-neutral.
- Re-bless Stage-12 GCI dashboards against the renamed `n_elements` field
  before any Stage-12 `production`-tagged run lands.
- Add the periodic-hill host-side wall-sampler in Stage 12; the case ships
  in Stage 07 as a registry stub for the V&V dashboard symmetry.
- The RunPod community-cloud rate table (`POD_TYPE_HOURLY_USD`) is a
  static snapshot of 2026-05 pricing; surface a `--hourly-rate-usd` CLI
  override so the cost-cap honours operator-tier pricing.
