---
stage: 06
stage_name: "Stage 06 — SU2 Adapter — Forcing the Abstraction"
status: partial
date_started: 2026-05-19
date_completed: 2026-05-19
session_duration_hours: 6.0
claude_code_version: "2.1.117 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "ea43950921aa9a3aabb4a69cf2dc7a8c09d2d837"
git_sha_end: "2e5d7af8a623d065ab683e4b7c118bf2f3bfddda"
stage_tag: v0.0.6
next_stage: 07
next_stage_name: "Stage 07 — PyFR + NekRS GPU Solvers"
---

# Stage 06 — SU2 Adapter — Forcing the Abstraction — DONE (partial) 2026-05-19

> Auto-loaded by the Stage 07 session as "BEFORE YOU START — READ".
>
> **The Solver protocol is generalised; SU2 v8 ships as the second concrete
> adapter; the TMR cases run through either solver; the transonic cases
> register; the cross-solver comparison emits a JSON+markdown report; CI gains
> `import-platform-only` and `vv-transonic`.**
>
> **Status is `partial`** for the same reason Stage 05 was: the SU2 SIF build
> and the SU2 cluster validation against the TMR + transonic cases are
> operator/cluster follow-ups, not in-session deliverables. Everything that
> can be verified host-side is — 113 unit/integration tests green, mypy
> `--strict` clean, ruff clean, OpenFOAM TMR numbers bit-unchanged after the
> refactor, `import aero` PLATFORM-NOT-HUB clean.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `containers/su2-v8.def` (SU2 v8 SIF) | ⚠️ | def + Dockerfile + build script ship; build is a cluster follow-up (no rootless-buildah here) — §3 |
| 2 | Build the SIF; sign; append SHA256 | ⚠️ | operator runs `scripts/build_su2_sif.sh` on aero-build — §7 |
| 3 | `aero/adapters/su2/{solver,schemas}.py` | ✅ | `SU2Solver(Solver)`, `SU2AirfoilSpec`/`SU2MeshFileSpec` discriminated union |
| 4 | Generalised `Solver` protocol at `aero/adapters/_base.py` | ✅ | ABC + `SolverProtocol`; shared handles/results — §2, ADR-006 |
| 5 | Refactor OpenFOAM onto the new base | ✅ | numbers bit-unchanged; `load()` now returns typed `SolveResult` — §2 |
| 6 | `aero[su2]` extras (`mpi4py`, `meshio`, numpy floor) | ✅ | independent of `aero[openfoam]` (guardrail 3) |
| 7 | TMR cases through SU2 (`tests/vv/test_tmr_*_su2.py`) | ⚠️ | wired and protocol-checked; `xfail(strict=False)` until cluster validates — §7 |
| 8 | Two transonic cases (`aero/vv/transonic/`) | ⚠️ | NACA0012 transonic ships with Cd reference; ONERA M6 ships with reference.md + needs DVC pull (mesh + Cp data) — §3, §6 |
| 9 | `aero/vv/cross_solver_compare.py` | ✅ | `compare_solvers` + `CrossSolverReport` (JSON + markdown) |
| 10 | `vv-smoke.yml` runs both solvers; `vv-transonic.yml` nightly | ✅ | both updated/new |
| 11 | ADR-006 | ✅ | `docs/adrs/ADR-006-solver-protocol-and-su2-adapter.md` |
| 12 | CONSTITUTION Invariant 7 — TYPED-CONVERGENCE-HISTORY | ✅ | amendment landed in this PR alongside ADR-006 |
| 13 | `import-platform-only` CI job | ✅ | new required-candidate workflow — operator promotes to required (§7) |
| 14 | Tag `v0.0.6` | ⚠️ | applied at PR merge (Stage 02–05 precedent) |

## 2. Decisions made

- **`Solver` shape — ABC + structural Protocol (both)** (ADR-006 §B). The
  `Solver` ABC owns shared concrete code (`__init__`, run-id/path
  computation, the `prepare` template method, `build_apptainer_exec`) and
  declares the five seams (`_write_case`, `mesh`, `run`, `load`,
  `wall_distribution`) abstract. `SolverProtocol` is the `runtime_checkable`
  structural contract the V&V harness types against; the ABC satisfies it
  structurally. `aero/vv/_base.SolverLike` aliases the canonical name (one
  source of truth — *rejected*: keeping two hand-maintained structural
  views).
- **`mesh` and `run` stay abstract, not template methods.** With two
  solvers their post-command verification (polyMesh vs. NELEM parse)
  differs enough that hoisting only the command-string would leave a
  near-empty base method. Revisit at the third solver (PyFR, Stage 07).
- **`load()` returns a typed `SolveResult`** carrying a typed
  `ConvergenceHistory(iteration, residual)` — *rejected*: `xr.Dataset`
  (couples every adapter to xarray and ships an unvalidated `.attrs` dict;
  FAIL-LOUD violation in spirit). This becomes new Invariant 7.
- **`ResultHandle.post_processing_host_path` → `output_host_path`** — the
  old name was OpenFOAM-specific. Three call sites updated.
- **`SU2Solver._write_case` dispatches across both spec families.** SU2
  consumes OpenFOAM's `CaseSpec`/`FlatPlateSpec`/`Bump2DSpec` (so the TMR
  cases run unchanged) and the SU2-native `SU2AirfoilSpec`/
  `SU2MeshFileSpec`. The dispatch fails loud on an unrecognised spec
  (`TypeError`).
- **SU2 SIF — two-step OCI-then-SIF (ADR-006 §C).** The unprivileged
  `aero-build` LXC cannot open sockets in an Apptainer `%post` build
  sandbox (Stage 02 §6); rootless `buildah`/`podman` on the same LXC *can*
  (slirp4netns). The `Dockerfile` source-builds SU2 v8 with autodiff,
  Mutation++, pysu2, OpenBLAS (no MKL — guardrail 6); the `.def`
  bootstraps from the resulting OCI archive, `%post` filesystem-only.
- **SU2 version — latest v8.x stable.** The build script captures the
  exact tag + commit SHA at build time and labels them into the image; the
  cluster-build follow-up records both here for the audit trail.
- **TMR through SU2 — `xfail(strict=False)`, no tolerance relaxed.** SU2
  has not yet cluster-validated against the TMR cases; the **cross-solver
  comparison report is the headline Stage-06 V&V deliverable**, not a
  green SU2 single-grid pass (operator Q&A 2026-05-19). Stage-05 precedent.
- **Transonic NACA 0012 reference** — Cd = 0.0079 (AGARD-AR-138 /
  Schmitt-Charpin), 5% tolerance (wider than TMR 3% because the SU2
  O-grid is not yet the grid-converged Cd mesh; tighten in Stage 12 GCI).
- **ONERA M6 — fails loud until data + 3D-slice land.** The Cp reference
  CSV at `data/references/transonic/onera_m6/cp_station_0.44.csv` is DVC-
  tracked; the host-side 3D wing-slice for `wall_distribution` is not yet
  implemented. `OneraM6.evaluate()` raises `BenchmarkError` — the
  `vv-transonic` test skips cleanly rather than producing a fake green.

## 3. Deviations from the stage plan

- **No SU2 SIF was built in-session.** The two-step build needs a host with
  rootless `buildah`/`podman` (network) and access to `/mnt/aero/containers`
  on the cluster; this Claude Code session ran host-side off the cluster.
  The build script + Dockerfile + def are committed; the operator runs
  `scripts/build_su2_sif.sh` on `aero-build`, the SHA256 line is appended to
  `containers/SHA256SUMS`, and `provenance-completeness` will then accept SU2
  runs (it currently rejects an SU2 run whose SHA is not in the manifest —
  the correct fail-loud behaviour).
- **No SU2 cluster validation.** Same precedent as Stage 05; the TMR + the
  transonic `xfail(strict=False)` tests run on the next nightly cluster pass.
- **ONERA M6 mesh asset (`data/meshes/su2/onera_m6.su2`) not committed
  directly** — it is ~3 MB ASCII and is DVC-tracked (committed `reference.md`
  documents the SU2-tutorial-repo source).

## 4. Environment / dependency / schema changes

- `pyproject.toml`: `aero[su2] = ["meshio>=5.3", "mpi4py>=4.0"]` (was empty).
- `aero/adapters/_base.py` — new module (the `Solver` ABC, the
  `SolverProtocol`, the shared handle/result types, `build_apptainer_exec`,
  the NFS-path constants). PLATFORM-NOT-HUB clean (stdlib + numpy + pydantic
  + loguru + `aero.orchestration._base` only).
- `aero/adapters/openfoam/`: `schemas.py` re-exports the shared handles +
  platform constants; `fields.py` re-exports `WallDistribution` from
  `_base`; `solver.py` is now `OpenFOAMSolver(Solver)` and `load()` returns
  `SolveResult` (was `xr.Dataset`). `ResultHandle.post_processing_host_path`
  renamed `output_host_path` (three call sites updated).
- `aero/adapters/su2/` — new package: `solver.py`, `schemas.py`,
  `mesh_writer.py` (airfoil O-grid, flat-plate, bump grid builders;
  geometric wall-normal spacing; `.su2` ASCII emitter), `cfg_writer.py`
  (compressible RANS configuration).
- `aero/vv/_base.SolverLike` is now an alias of `aero.adapters._base.SolverProtocol`.
- `aero/vv/transonic/` — new package with `TRANSONIC_CASES` registry.
- `aero/vv/cross_solver_compare.py` — new module.
- `aero/vv/tmr/{flat_plate,bump_2d}.py` call `solver.wall_distribution(...)`
  rather than importing `extract_wall_distributions` directly.
- `aero/cli.py` — `--solver {openfoam,su2}` on both `aero run` and `aero vv
  run`; `_REQUIRED_MODULES_BY_SOLVER` per-solver imports; `aero vv list`
  shows both TMR and transonic registries.
- `containers/su2-v8.{Dockerfile,def}` + `scripts/build_su2_sif.sh` — new.
- `data/references/transonic/{naca0012_transonic,onera_m6}/reference.md` +
  `naca0012_transonic/cd.csv` — new.
- `data/meshes/su2/reference.md` — new (mesh asset is DVC-tracked).
- `CONSTITUTION.md`: new Invariant 7 — TYPED-CONVERGENCE-HISTORY.
- `tests/conftest.py`: `su2_sif_present`, `su2_extra_installed` fixtures.
- `tests/vv/conftest.py`: `vv_cluster_ready_su2`, `vv_runner_su2` fixtures
  (the OpenFOAM `vv_runner` is unchanged in semantics).
- `tests/stage_06/` — new directory: `test_solver_protocol.py`,
  `test_su2_adapter.py`, `test_cross_solver_compare.py`.
- No aero LXC / shared-service changes. No Postgres schema change.

## 5. CI/CD changes

- `.github/workflows/import-platform-only.yml` — **new** required-candidate
  workflow. Fresh venv, `pip install -e .` (no extras), asserts
  `import aero` succeeds with **no** banned modules loaded
  (xarray/scipy/mlflow/pyfoam/ofpp/torch/jax/physicsnemo/meshio/mpi4py).
  Promote to required on `main` after the v0.0.6 merge (operator follow-up).
- `.github/workflows/vv-smoke.yml` — installs
  `aero[openfoam,su2,provenance,vv,dev]`; the test selector now picks up
  both stage_05 (OpenFOAM) and stage_06 (SU2) TMR paths via the shared
  `vv` + `slow` markers.
- `.github/workflows/vv-transonic.yml` — **new** nightly-only workflow
  (cron `0 6 * * *`, plus `workflow_dispatch`). Runs the transonic cases
  through SU2 on the self-hosted `vv` runner; not PR-gating.
- `vv-required.yml` filter already covers `aero/adapters/**` and
  `aero/vv/**` — SU2 paths gate automatically without a workflow change.
- The five existing required checks (lint/type/test/docs-sync/commit-lint)
  are unchanged.

## 6. Gotchas discovered

- **The unprivileged-LXC Apptainer build sandbox cannot open sockets —
  *but* rootless buildah/podman on the same LXC can** (slirp4netns is not
  the build sandbox's hardened user-namespace network). Stage 02 §6
  established the first half; this stage's two-step SU2 build leans on the
  second half. ADR-006 §C records the decision.
- **`SpecLike` as a pydantic field type needs `arbitrary_types_allowed=True`
  on the containing model.** A `runtime_checkable` Protocol with a single
  data attribute (`name: str`) validates via `hasattr` at the pydantic
  boundary; without `arbitrary_types_allowed`, pydantic refuses the Protocol
  type. Documented in `aero/adapters/_base.py:CaseDir`.
- **SU2 v8 `rms[Rho]` is base-10-log-scaled in `history.csv`** — Invariant 7
  asks for the *monitored* residual; we record SU2's native rms as-is. The
  cross-solver comparison does not compare residuals (it compares
  Cd/Cl/Cp). Documented in `SU2Solver.load`'s docstring.
- **SU2's `surface_flow.csv` contains exactly the `MARKER_PLOTTING` markers
  merged** — for our 2D cases that is one wall, so `wall_distribution(...,
  patch=...)` ignores `patch` and returns the whole file's contents.
  Documented inline.
- **3D wing-slice (ONERA M6) extraction is not in Stage 06.** The host-side
  `wall_distribution` for a 3D wing needs an η-station slicing step (a `y`-
  slice on `surface_flow.csv`); not implemented in this stage. `OneraM6.
  evaluate()` raises `BenchmarkError` so the test skips cleanly. Flagged for
  a follow-up.
- **The `aero[openfoam]` extra still includes `xarray`** even though
  `load()` no longer returns one — kept for downstream field
  post-processing tooling. Removing it is an unrelated cleanup; not Stage 06.
- **`SolverLike` import via `as` requires module-level re-export** —
  `from aero.adapters._base import SolverProtocol as SolverLike` is not
  treated as an explicit re-export by mypy in strict mode; using
  `from aero.adapters._base import SolverProtocol` followed by `SolverLike
  = SolverProtocol` is. Documented at the top of `aero/vv/_base.py`.

## 7. Open items for the next stage (and beyond)

**Cluster follow-ups (operator):**
1. **Build the SU2 SIF** — run `scripts/build_su2_sif.sh` on `aero-build`
   (or any host with rootless buildah + access to `/mnt/aero/containers`),
   sign it, append the SHA256 to `containers/SHA256SUMS`. Record the SU2
   tag + commit SHA the OCI build captured.
2. **Mirror the ONERA M6 mesh asset** to `data/meshes/su2/onera_m6.su2` as
   DVC-tracked (the SU2 tutorial repo's BSD mesh).
3. **Fetch the transonic Cp reference data** for ONERA M6 (at least
   η = 0.44 to satisfy the test).
4. **Run the SU2 TMR + transonic suites on the cluster.** Update the
   `xfail` markers as cases pass.
5. **Promote `import-platform-only` to a required status check** on
   `main` (branch protection — `gh api -X PATCH .../branches/main/protection`).
6. **Merge the Stage-06 PR; tag `v0.0.6`; publish the Release.**

**Stage-05 follow-ups still open:**
- Fixing the OpenFOAM TMR open items (TE pressure drag, bump pressure
  solver, flat-plate TMR Cf data fetch) — these remain Stage-05's open
  items; Stage 06 deliberately did not touch them (operator Q&A).
- Promote `vv-required` to a required status check.

**Stage 07 (PyFR + NekRS):**
- The third concrete solver(s) — expect the seams flagged in ADR-006
  §Consequences to bend:
  - `mesh()` as a phase (PyFR uses `gmsh + pyfr import + pyfr partition`;
    NekRS uses `.re2`/`.par` + `genmap`);
  - `build_apptainer_exec` needs GPU `--nv` and MPI `mpirun -n N` flags;
  - `MeshHandle.n_cells` is FV-centric — PyFR/NekRS count elements
    × polynomial order (likely rename or add `n_dof`);
  - `ConvergenceHistory(iteration, residual)` is steady-RANS; time-accurate
    GPU solvers want `TimeHistory(t, monitor)`;
  - `SolveResult`'s hardcoded `cd`/`cl` is over-fit — ERCOFTAC internal
    flows want a `scalars: dict[str, float]` field validated by case.
- Stage 06's `Solver` base will need a controlled extension; do not
  pre-design it.

## 8. Pointers for the next session

- **Read first:** this handoff; `docs/adrs/ADR-006-solver-protocol-and-su2-adapter.md`;
  CLAUDE.md (the Stage-06 entry the next stage will append); ADR-003 §"Out
  of scope" (which Stage 06 lifted item-2 from).
- **Do not re-read:** `aero/adapters/_base.py` and `aero/adapters/su2/`
  unless extending — they are complete and unit-tested.
- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv pip install -e ".[openfoam,su2,provenance,vv,dev]"
  .venv/bin/pytest -q tests/unit tests/vv tests/stage_06   # 113 pass
  .venv/bin/aero vv list                                   # five cases
  ```
  PLATFORM-NOT-HUB probe:
  ```bash
  python -c "import aero, aero.adapters._base, aero.vv; import sys;
  print([m for m in ('xarray','scipy','mlflow','pyfoam','torch','jax','meshio','mpi4py')
         if m in sys.modules])"
  # -> []
  ```

## 9. Artifacts produced

Branch `stage-06/su2-adapter` (`ea43950`→`2e5d7af`, 4 commits):

- **Solver protocol:** `aero/adapters/_base.py` (new); OpenFOAM adapter
  refactored onto `Solver`; `aero/vv/_base.SolverLike` aliased.
- **SU2 adapter:** `aero/adapters/su2/{__init__,solver,schemas,
  mesh_writer,cfg_writer}.py`.
- **V&V:** `aero/vv/transonic/{__init__,naca0012_transonic,onera_m6}.py`;
  `aero/vv/cross_solver_compare.py`; SU2 TMR + transonic test files under
  `tests/vv/`; `data/references/transonic/...`; `data/meshes/su2/reference.md`.
- **Container:** `containers/su2-v8.{Dockerfile,def}` + `scripts/build_su2_sif.sh`.
- **CLI:** `--solver {openfoam,su2}` in `aero/cli.py`; per-solver required-
  modules; `aero vv list` shows both registries.
- **CI:** `.github/workflows/import-platform-only.yml` (new),
  `vv-transonic.yml` (new), `vv-smoke.yml` (both-solver).
- **Tests:** `tests/stage_06/`; `tests/vv/test_tmr_*_su2.py`;
  `tests/vv/test_transonic_{naca0012,onera_m6}.py`.
- **Docs:** `docs/adrs/ADR-006-*.md`; `CONSTITUTION.md` Invariant 7;
  CHANGELOG `v0.0.6`.

## 10. Confidence / risk note

- **High confidence:** the `Solver` protocol shape — ABC + Protocol satisfies
  both adapters cleanly; mypy `--strict` passes; isinstance asserts pass; the
  OpenFOAM refactor is behaviour-preserving (Cd/Cf/Cp test inputs unchanged,
  85 → 113 hermetic tests green). PLATFORM-NOT-HUB probe is clean — `import
  aero` + the adapter base + V&V pulls *no* solver/ML modules. CI workflows
  validate.
- **Medium confidence:** the SU2 `.su2` mesh writer produces structurally
  valid meshes (right NELEM/NPOIN, marker counts match boundary lengths,
  positive cell areas verified on samples), but mesh *quality* on the
  airfoil O-grid is not yet tuned against converged SU2 Cd — it is the
  algebraic transfinite blend the docstring describes, no smoothing or
  orthogonalisation. Tightening is Stage-12 GCI work.
- **Low confidence / not yet established:** whether SU2 single-grid runs
  hit the TMR / transonic tolerances at the spec defaults (n_surface,
  n_normal, first_cell_height) the adapter ships. This is exactly the
  cluster validation Stage 06 leaves as `partial`; the cross-solver report
  is the honest signal until then.
- **Outstanding risk:** the seams ADR-006 §Consequences flagged for PyFR/
  NekRS are real — `mesh()`-as-a-phase and `ConvergenceHistory`-as-steady-
  residual are the two most likely to bend. Stage 07 will need a controlled
  extension to `Solver`/`SolverProtocol`; the third data point is what
  decides the right shape, exactly as ADR-003 said the second one was.
