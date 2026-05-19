# ADR-003 — OpenFOAM Walking-Skeleton Scope

- **Status:** accepted
- **Date:** 2026-05-19
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 03)
- **Stage:** 03
- **Supersedes:** —

## Context and problem statement

Stage 03 delivers Cockburn's *walking skeleton* (Pass 3 §5.1): one thin
end-to-end slice that exercises every layer the platform will rely on —
containerised CFD, remote execution, basic provenance, shared storage, and
result reporting. Concretely the slice is:

> STL-free NACA 0012 geometry → Apptainer OpenFOAM-ESI `simpleFoam` on an aero
> LXC → MLflow run → reported drag coefficient.

The risk being retired is *integration* risk — a flaky SIF build, `apptainer
exec` over SSH, MLflow refusing a payload, a result parser that drifts. The
walking skeleton surfaces those failures now, at Stage 03, instead of at
Stage 09 when a surrogate is being trained on data this pipeline produced.

This ADR records **what is deliberately in vs out of scope**, and the
**implementation decisions and deviations** from the Stage 03 prompt, so that
later stages inherit an explicit, honest boundary rather than a guess.

## Decision drivers

- De-risk the whole architecture in a single pass.
- **Avoid premature abstraction.** The right shape of `Solver` and `Executor`
  cannot be known from one implementation; a second solver (SU2, Stage 06)
  and cloud executors (Stage 13) are the forcing functions.
- The Stage 02 constraints: the unprivileged-LXC Apptainer build sandbox has
  no network in `%post`; non-root `apptainer exec` fails in the unprivileged
  LXC (Stage 02 handoff §6).
- The Stage 03 prompt's deliverables, realised where the environment allows.

## Considered options

1. **Walking skeleton** — one concrete, OpenFOAM-only slice; one `Executor`
   implementation; no shared abstraction. *(chosen)*
2. **Generalised platform now** — design `Solver`/`Executor` base classes and
   a multi-solver abstraction up front.
3. **Status quo** — stop at the Stage 02 container pipeline; no CFD slice.

## Decision outcome

Chose **Option 1, the walking skeleton**, because a single concrete slice
retires integration risk without committing to abstractions that one
implementation cannot validate.

**In scope (Stage 03):** the OpenFOAM-ESI SIF; an OpenFOAM-only adapter
(`prepare`/`mesh`/`run`/`load`); one `Executor` (`LocalSSHExecutor`); the
`aero run naca0012` CLI; a minimal MLflow logger; the NACA 0012 reference
case; unit + smoke tests; the `vv-smoke` CI workflow.

**Out of scope — deliberately deferred:**

| Deferred item | To stage | Why not now |
|---|---|---|
| Cloud / Slurm executors | 13 | One `Executor` impl cannot reveal the right multi-backend shape. |
| Multi-solver `Solver` base class | 06 | SU2 is the second data point that defines the abstraction. |
| Four-fold provenance (`dvc_input_hash`, `config_hash`) | 04 | Needs DVC-tracked inputs + Hydra config resolution. |
| Remote MLflow tracking server | 04 | `aero-mlflow` server stands up in Stage 04; Stage 03 logs to a local `mlruns/`. |
| DVC tracking of `data/references/` | 04 | DVC remote + pipeline wiring is Stage 04. |
| STL geometry / `snappyHexMesh` | 06+ | A 2D `blockMesh` mesh needs no STL. |
| Tightening the ±25% Cd band | 05 | Stage 05 validates against NASA TMR reference data. |
| Ofpp field/mesh post-processing | 05 | Stage 03 needs only force coefficients. |

### Consequences

- **Positive:** the platform demonstrably runs CFD end-to-end; integration
  failure modes are now known; later stages extend a working skeleton.
- **Negative:** `OpenFOAMSolver` and `LocalSSHExecutor` are concrete and will
  be refactored when Stages 06/13 introduce the real abstractions; the mesh
  and tolerances are walking-skeleton-grade, not publication-grade.
- **Neutral / follow-up:** the deferred items above are the Stage 04–13
  backlog; `mlflow_basic.py` is explicitly interim.

## Implementation decisions & deviations from the stage prompt

1. **O-grid mesh, not a C-grid.** The Stage 03 prompt asks for "a 2D extruded
   structured-block mesh via `blockMesh`". A single-wrapping-block C-grid is
   *degenerate* under blockMesh's topology check when the trailing edge is
   closed (the two TE corners coincide); a conforming multi-block C-grid is
   considerably more complex. Stage 03 ships a **four-block O-grid** — four
   positive-volume hexes, each wrapping one airfoil quarter, distinct vertices
   throughout, no `mergePatchPairs`. Trade-off: an O-grid is more skewed at
   the sharp TE and its wake is not grid-aligned; acceptable for a
   skin-friction-dominated AoA-0° smoke case.
2. **Analytic geometry, no STL.** `blockMesh` builds the airfoil surface from
   a coordinate curve; STL is only a `snappyHexMesh` input. The prompt's
   "store geometry STL" is satisfied instead by `data/references/naca0012/
   naca0012.csv` — the analytic NACA 4-digit coordinates, reproducible from
   `n_points` alone, no opaque binary.
3. **`load()` parses `coefficient.dat` with `numpy.loadtxt`, not Ofpp.** The
   `forceCoeffs` function object writes a columnar ASCII file, not an
   OpenFOAM field/mesh file (Ofpp's domain). Ofpp ships in the `openfoam`
   extra but is unused in Stage 03; it is used from Stage 05 for field-level
   post-processing (y+, surface pressure).
4. **`mlflow` lives in the `aero[openfoam]` extra.** The whole skeleton is
   gated on that extra, so `pip install -e .[openfoam]` is one step. Stage 04
   introduces the dedicated `provenance` extra and four-fold logger, which
   supersede `mlflow_basic.py`.
5. **`run_long.sh` accepts a `[user@]alias` target.** Solver SIFs must run as
   the LXC root; `run_long.sh` previously submitted only as each alias's
   default user. `is_alias` now strips an optional `user@` prefix —
   backward-compatible, no other call site changed.
6. **`mesh()` takes the `Executor` as a parameter.** The prompt's
   `mesh(case_dir)` signature omitted it, but meshing runs `blockMesh` inside
   the SIF on a remote host exactly as the solve does — `mesh(case_dir,
   executor)` is symmetric with `run(case_dir, executor)`.
7. **Solver SIFs run as the LXC root.** Non-root `apptainer exec` fails in the
   unprivileged aero LXC (Stage 02 §6); `LocalSSHExecutor` therefore SSHes to
   `root@aero-build`. Resolving non-root execution is left to a later stage.
8. **The case runs to `endTime`.** The pressure residual plateaus around
   1.5e-3 because of TE mesh skewness, so `residualControl` is not met; the
   drag coefficient is nonetheless steady (settled by ≈ iteration 600). The
   `iterations_to_convergence` metric therefore records the `endTime`. A
   higher-quality Stage 05 mesh is expected to converge on residuals.
9. **`pyproject.toml` `version` stays `0.0.1`.** Per Stage 02's precedent, the
   git tags `v0.0.NN` are the stage markers; the package version bumps to
   `0.1.0` after Stage 16.

## Pinned versions (Hard Rule 8)

| Dependency | Pin | Note |
|---|---|---|
| `opencfd/openfoam-default` | `:2412` @ `sha256:1ba02114b1c025c370f2e269a07677c16c9bea8d990fcd75ac8378aff9d41b50` | OpenFOAM-ESI v2412; Docker Hub OCI index digest. |
| `pyfoam` | `>=2023.7` | The Stage 03 prompt said `>=2024.5`; **no such release exists on PyPI** — 2023.7 is the latest. Pin relaxed. |
| `ofpp` | `>=0.12` | Resolved to 0.12. |
| `xarray` | `>=2024.10` | — |
| `mlflow` | `>=2.20` | Interim home is the `openfoam` extra (decision 4). |

## Links

- Stage prompt: `STAGE-03-walking-skeleton-openfoam.md`
- Project brief: `00-CONTEXT-project-brief.md`
- Related ADR: ADR-002 (Proxmox topology — the build/run LXCs, signing key)
- Related handoff: `docs/handoffs/STAGE-02-proxmox-and-container-pipeline-DONE-2026-05-19.md`
- External: Ladson, NASA TM-4074 (1988) — NACA 0012 reference Cd
