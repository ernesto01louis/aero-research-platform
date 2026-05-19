# ADR-006 — Solver Protocol Generalisation and SU2 v8 Adapter

- **Status:** accepted
- **Date:** 2026-05-19
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent
  (Stage 06)
- **Stage:** 06
- **Supersedes:** the "no `Solver` base class — generalise from the second
  solver" out-of-scope item in ADR-003 (Stage 06 is that second solver).
  ADR-003 otherwise stands.

## Context and problem statement

Stage 03 shipped one fully-concrete solver (`OpenFOAMSolver`); Stage 05 ran
the TMR V&V cases through it. Single-solver abstractions are wrong by default
(Pass-3 best practices, ADR-003) — the right shape of a multi-solver
`Solver` protocol only emerges from the *second* concrete implementation.

Stage 06 adds **SU2 v8** as that second solver and unlocks the compressible /
transonic regime the incompressible `simpleFoam` adapter cannot reach. This
ADR records four decisions:

1. The shape of the generalised `Solver` protocol (taken from the OpenFOAM ∩
   SU2 intersection — *not* speculatively for PyFR/NekRS/JAX-Fluids).
2. Why SU2 v8 was chosen as the second solver, and the version pin.
3. The two-step OCI-then-SIF container build pattern for SU2.
4. The new CONSTITUTION Invariant 7 — typed convergence history — that
   becomes true *because* of this design.

## Decision drivers

- **Pass-3 anti-premature-abstraction.** The second concrete implementation
  defines the abstraction; PyFR/NekRS/JAX-Fluids (Stages 07–08) deliberately
  do *not* enter the design.
- **PLATFORM-NOT-HUB (Invariant 1) / HEAVY-DEPS-IN-OPTIONAL-EXTRAS-ONLY
  (Invariant 4).** `aero/adapters/_base` may import nothing solver-specific;
  `aero/vv` must keep typing against a structural contract.
- **FAIL-LOUD (Invariant 2).** The `load()` return type must be a typed
  schema, not an untyped solver-native container (`xr.Dataset.attrs[...]`).
- **GPL/BSD/Apache only (Invariant 5).** No Intel MKL in the SU2 build.
- **Honest scope.** Cluster validation of SU2 against the TMR cases is the
  Stage-06 *partial* outcome — same precedent as Stage 05.

## Considered options

### A. Second solver — SU2 v8 vs. Code_Saturne vs. Code_Aster

- **SU2 v8** (chosen). Compressible RANS + discrete adjoint + Python wrapper
  (`pysu2`) + the Mutation++ hypersonic path; LGPL-2.1; widely-used and
  benchmarked against AIAA prediction workshops; the SU2 tutorial repository
  ships BSD-licensed meshes (ONERA M6) the platform can mirror.
- **Code_Saturne** — EDF's open-source CFD code; GPL; strong on incompressible
  and atmospheric flow. Rejected: compressible/transonic is the regime
  Stage 06 is *for*; SU2 is the canonical open-source compressible RANS code,
  and its discrete-adjoint pipeline is what Stage 12 UQ + Stage 14 agentic
  optimisation will lean on.
- **Code_Aster** — primarily structural mechanics; out of scope.

The Mutation++ inclusion (built, not yet exercised in Stage 06) pins the
future-hypersonic path at near-zero present cost.

### B. `Solver` shape — pure Protocol vs. ABC vs. both

- **Pure Protocol (PEP 544).** Loses `@abstractmethod` enforcement; a
  half-built adapter ships silently.
- **ABC only.** Couples `aero/vv` to the concrete adapter package's evolution
  (a future leak risk).
- **Both — ABC + `runtime_checkable` Protocol (chosen).** The `Solver` ABC
  owns the shared concrete code (run-id/path computation, the `prepare`
  template method, `build_apptainer_exec`) and declares the seams abstract;
  `SolverProtocol` is the *structural* contract `aero/vv` types against.
  The ABC structurally satisfies the Protocol — one `isinstance` test per
  adapter pins it, and `aero/vv/_base.SolverLike` aliases the canonical name.

### C. SU2 SIF build — source-in-`%post` vs. prebuilt upstream vs. two-step

- **Source build inside `%post`.** Cannot run: the Apptainer build sandbox
  inside the unprivileged `aero-build` LXC cannot open sockets (Stage 02 §6).
- **Bootstrap from upstream `su2code/su2`.** Insufficient: the upstream
  image may not include `pysu2` + autodiff + Mutation++ together, and the
  Stage-06 prompt is explicit about those flags.
- **Two-step OCI-then-SIF (chosen).** Rootless `buildah`/`podman` on the
  same LXC uses `slirp4netns` and *is* network-capable; `containers/
  su2-v8.Dockerfile` source-builds SU2 with the required flags into a local
  OCI image; `containers/su2-v8.def` bootstraps from `oci-archive`,
  `%post` filesystem-only. Identical bind targets and signing flow as the
  OpenFOAM SIF.

### D. `load()` return type — `xr.Dataset` vs. duck-typed `.attrs` vs.
typed `SolveResult` (chosen)

- **`xr.Dataset`.** OpenFOAM's Stage-03 choice; couples every adapter to
  `xarray` (would force it into `aero[su2]`) and exposes an unvalidated
  `.attrs` dict — a FAIL-LOUD violation in spirit.
- **Duck-typed `.attrs`.** Perpetuates a stringly-typed surface.
- **Typed `SolveResult` (chosen).** A strict pydantic model carrying
  `cd`, `cl`, `iterations_to_convergence`, `final_residual`, `source`, and a
  typed `ConvergenceHistory(iteration, residual)`. Becomes the new
  Invariant 7. Callers (TMR cases, CLI, smoke test) updated to read typed
  fields, not dict keys.

## Decision

1. **`aero/adapters/_base.py`** holds the `Solver` ABC + `SolverProtocol`,
   the shared `CaseDir` / `MeshHandle` / `ResultHandle` (the last with
   `output_host_path`, renamed from the OpenFOAM-specific
   `post_processing_host_path`), `SolveResult`, `ConvergenceHistory`,
   `WallDistribution`, `build_apptainer_exec`, and the NFS-path constants.
   Imports: only stdlib, numpy, pydantic, loguru, `aero.orchestration._base`.

2. **OpenFOAM** subclasses `Solver`; its `load()` returns a `SolveResult`
   with the per-iteration residual series from the simpleFoam log; its
   `wall_distribution()` delegates to `extract_wall_distributions`. Numbers
   are bit-unchanged from Stage 05 (no behaviour regression — guardrail 2).

3. **SU2 v8 adapter** at `aero/adapters/su2/` consumes both the
   OpenFOAM TMR specs (`CaseSpec`, `FlatPlateSpec`, `Bump2DSpec` — so the
   Stage-05 TMR cases run through either solver) and SU2-native specs
   (`SU2AirfoilSpec`, `SU2MeshFileSpec`); writes native `.su2` structured
   meshes with geometrically-clustered wall-normal spacing; writes a
   compressible RANS `.cfg` (Roe convective at M ≥ 0.3, JST below); parses
   `history.csv` and `surface_flow.csv`. `aero[su2]` extras: `mpi4py`,
   `meshio` — independent of `aero[openfoam]` (guardrail 3); `pysu2` lives
   inside the SIF.

4. **SU2 version pin** — latest v8.x stable. The build script captures the
   exact git tag + commit SHA at build time and labels them into the OCI
   image (`org.aero.su2.version`, `/opt/su2/.su2-commit`); the
   post-stage handoff records both. Subsequent stages do not change this
   pin without an ADR amendment.

5. **OpenBLAS, not Intel MKL** (guardrail 6 / Invariant 5). The Dockerfile
   `apt-get install`s `libopenblas-dev` and lets the SU2 build link against
   it. No proprietary blob enters the SIF.

6. **`mesh` and `run` stay abstract** — not template methods. With only two
   concrete solvers their post-command verification (polyMesh existence vs.
   `NELEM`-count parse) differs enough that hoisting only the command-string
   construction would leave a near-empty base method. Revisit at the third
   solver (PyFR, Stage 07).

7. **CONSTITUTION Invariant 7 — TYPED-CONVERGENCE-HISTORY.** Every solver
   adapter's `load()` returns a typed `SolveResult` carrying a typed
   `ConvergenceHistory`; never a solver-native container or `.attrs` dict.
   The V&V harness, the cross-solver compare, and the Stage-12 UQ layer
   read one shape.

8. **Stage-06 V&V outcome is `partial`** — same as Stage 05. SU2 cluster
   validation against the TMR cases is the cluster follow-up; the
   `tests/vv/test_tmr_*_su2.py` tests are `xfail(strict=False)` until the
   first cluster run lands. The cross-solver comparison report is the
   headline Stage-06 V&V deliverable.

## Consequences

### Positive

- `aero/vv` and the harness types against one structural Protocol; a future
  test double or a Stage-09 surrogate satisfies it without touching either
  adapter.
- `xarray` is no longer in any solver's return type — the OpenFOAM extra
  could drop it eventually (left in for downstream post-processing).
- Compressible/transonic aero is unlocked; the AGARD-AR-138 / Schmitt-Charpin
  reference set enters the V&V dashboard.
- `import-platform-only` becomes a structurally-enforced CI check (Stage 03
  named it as out-of-scope-for-now; Stage 06 makes it real).

### Negative / known limitations

- The `Solver` shape is the *OpenFOAM ∩ SU2* intersection. Seams likely to
  bend at Stage 07 (PyFR/NekRS): `mesh()` as a phase (PyFR uses
  `gmsh + pyfr import + pyfr partition`); `build_apptainer_exec`'s fixed
  signature (GPU `--nv`, MPI launch); `MeshHandle.n_cells` (PyFR/NekRS count
  elements × polynomial order); `ConvergenceHistory` as iteration-vs-residual
  (PyFR/NekRS/JAX-Fluids are time-accurate); `SolveResult`'s required
  `cd`/`cl` (no internal-flow / heat-transfer case yet).
- The SU2 O-grid the adapter generates is not yet the grid-converged Cd
  grid for transonic airfoils — a GCI mesh sweep tightens this in Stage 12.
- ONERA M6 `wall_distribution` needs a 3D wing-slice extraction not yet
  implemented host-side; the case raises `BenchmarkError` and the test
  skips cleanly (no fake green).
- The SU2 SIF SHA256 is recorded into `containers/SHA256SUMS` only after
  the cluster build runs; `provenance-completeness` rejects an SU2 run
  whose SHA is not in the file — the correct fail-loud behaviour, not a
  regression.

## Open questions / future work

- Promote `import-platform-only` to a required check on `main` (operator
  follow-up — branch protection).
- Update `provenance-completeness` to recognise the SU2 SHA once the SIF
  is built and the SHA256SUMS line lands.
- Add the OpenFOAM `rhoCentralFoam` transonic cross-check (best-effort,
  flagged in the cross-solver report) — Stage-06 stretch.
- Make `aero vv run --case <transonic case> --cross-solver` invoke
  `aero.vv.cross_solver_compare.compare_solvers` from the CLI directly.
