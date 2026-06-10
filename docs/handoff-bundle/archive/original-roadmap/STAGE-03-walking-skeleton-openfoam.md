# STAGE-03: Walking Skeleton — OpenFOAM end-to-end

## REQUIREMENTS THIS STAGE DELIVERS

Cockburn's walking skeleton (Pass 3 §5.1): a *single* end-to-end slice exercising
containerization, CFD execution, basic provenance, storage, and reporting. For this
platform, the slice is:

**STL → Apptainer-OpenFOAM-ESI `simpleFoam` on Proxmox LXC → MLflow run (basic, full
provenance comes in Stage 04) → reported drag coefficient.**

After this stage, you can demonstrate the platform runs CFD. Everything else is
adding flesh to the skeleton.

## ROLE

You are building the first CFD adapter and the first end-to-end pipeline. You will
NOT generalize the abstraction at this point — that comes in Stages 04 and 06, when
the second solver forces the abstraction. Premature abstraction here is a known
failure mode (you don't yet know the right shape).

## GOAL

1. Author `containers/openfoam-esi.def` — Apptainer SIF recipe based on
   `opencfd/openfoam-default:2412` (or operator-confirmed version). Bootstrap from
   `docker://`, install Python 3.12 + pyfoam + Ofpp inside, expose
   `/opt/openfoam` PATH, set entrypoint to bash.
2. Build the SIF on `aero-build` via `tmux` long-running pattern. Sign it. Append
   SHA256 to `containers/SHA256SUMS`.
3. Author the first OpenFOAM adapter at `aero/adapters/openfoam/`:
   - `__init__.py` exports `OpenFOAMSolver`
   - `solver.py` — `OpenFOAMSolver` class with methods:
     - `prepare(case: CaseSpec) -> CaseDir`: writes constant/, system/, 0/
       directories from a `CaseSpec` (pydantic strict)
     - `mesh(case_dir: CaseDir) -> MeshHandle`: runs `snappyHexMesh` inside the SIF
       via `apptainer exec`
     - `run(case_dir: CaseDir, executor: Executor) -> ResultHandle`: runs
       `simpleFoam` inside the SIF via the executor abstraction
     - `load(result: ResultHandle) -> xarray.Dataset`: parses force coefficients
       via Ofpp
   - `schemas.py` — `CaseSpec`, `CaseDir`, `MeshHandle`, `ResultHandle` pydantic
     models, all `extra='forbid'`
4. Author a minimal `Executor` interface at `aero/orchestration/_base.py` with
   ONE concrete implementation: `LocalSSHExecutor` that runs commands on a named
   SSH host (initially `aero-build`). The cloud executors come in Stage 13. This
   is intentional: prove the interface shape with one impl, then generalize.
5. Add `aero[openfoam]` to `pyproject.toml`: `pyfoam>=2024.5`, `ofpp>=0.12`,
   `xarray>=2024.10`.
6. Author the first reference case: NACA 0012, Re=6e6, Mach 0.15 (incompressible,
   `simpleFoam`, k-omega SST, y+ < 1, single AoA 0°). Expected Cd ≈ 0.0079
   (Ladson NASA TM-4074 reference). Store geometry STL under
   `data/references/naca0012/` (DVC-tracked, but DVC integration full wiring is
   Stage 04; for now use a simple Git-LFS or a small enough file in tree).
7. Author the runner CLI at `aero/cli.py` (typer): `aero run naca0012 --executor
   local-ssh` returns Cd in <10 minutes on the build LXC.
8. Author `aero/provenance/mlflow_basic.py` — a minimal MLflow logger that logs
   `git_sha`, `container_sif_sha256`, `case_name`, `solver_version`, plus metrics
   (`cd`, `cl`, `iterations_to_convergence`, `final_residual`). Full four-fold
   provenance comes in Stage 04.
9. Author `tests/stage_03/test_naca0012_smoke.py` — runs the case, asserts Cd is
   within 25% of reference. Marked `slow`, skipped in unit tests, run in the
   `vv-smoke` workflow which is now real (it was a placeholder in Stage 01).
10. Author `tests/unit/test_openfoam_adapter.py` — mocks `apptainer exec` and
    asserts the adapter produces the right command lines.
11. Update `README.md` quick-start section to include a `aero run naca0012` example
    (gated on `aero[openfoam]` extras installed).
12. Author ADR-003 documenting the walking-skeleton scope and explicitly listing
    what is INTENTIONALLY OUT OF SCOPE: cloud executors, DVC inputs, full
    provenance, multi-solver abstraction. Stages 04, 06, 13 will lift these.
13. Tag `v0.0.3`.

## WHY

A walking skeleton de-risks the *entire* architecture in one pass. If Apptainer
SIF build fails, if `apptainer exec` from a Python process via SSH is flaky, if
pyfoam's API has drifted, if MLflow can't accept Pydantic-serialized configs — we
find out *now*, not in Stage 09 when we're trying to train a surrogate on data
this pipeline produces.

Avoiding premature abstraction matters. The shape of `Solver`, `Executor`,
`CaseSpec` is unknown until we have *two* solvers (Stage 06). Build one concrete
implementation now, and in Stage 06 the second solver will tell us what's
naturally a base class and what's a leaky abstraction.

## HOW

- The OpenFOAM SIF build can take 30+ minutes. Use the `scripts/run_long.sh`
  pattern from Stage 02. Don't tail the log in the agent context.
- Use `apptainer exec` not `apptainer run`. We always want to pass an explicit
  command and capture its output.
- NACA 0012 mesh: start with a 2D extruded structured-block mesh via
  `blockMesh` — easier than snappyHexMesh for a smoke test. The full 3D + SHM
  pipeline can come later (Stage 06+).
- For provenance: don't try to do everything Stage 04 will do. Just log
  `git_sha` (from `git rev-parse HEAD`), `container_sif_sha256` (from
  `containers/SHA256SUMS`), and the metric. DVC integration is Stage 04.
- For the CLI: `typer` is in base deps. One subcommand for now: `aero run <case>`.
- Resist scope creep. If you're tempted to add a second case ("just the flat
  plate too"), STOP. One case suffices for the smoke test. Stage 05 adds the
  V&V harness with multiple cases.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-03-walking-skeleton-openfoam.md` (this file)
- `docs/handoffs/STAGE-02-*-DONE-*.md`
- `docs/architecture/proxmox-topology.md` (to know which LXC runs the SIF)
- `containers/SHA256SUMS` to see what's already there

## GUARDRAILS — DO NOT

1. Do NOT generalize the `Solver` interface beyond what OpenFOAM needs. Stage 06
   does the generalization with SU2 as the forcing function.
2. Do NOT install OpenFOAM on the host or in any LXC outside the SIF. All
   OpenFOAM execution goes through `apptainer exec`.
3. Do NOT pull OpenFOAM source for a custom build in this stage. Use the
   upstream OCI image as the SIF base.
4. Do NOT add cloud GPU executors. `LocalSSHExecutor` only.
5. Do NOT skip the Ofpp parsing step in favor of grepping `log.simpleFoam`. The
   walking skeleton must demonstrate the *full* path from solve to typed result.
6. Do NOT promote the walking skeleton to "production" — keep ADR-003's
   "out-of-scope" list explicit so the next stages know what they're inheriting.

## DELIVERABLES

- [ ] `containers/openfoam-esi.def` builds successfully on `aero-build`
- [ ] SHA256 of the SIF appended to `containers/SHA256SUMS`
- [ ] `pip install -e .[openfoam,dev]` succeeds
- [ ] `pytest -q tests/unit/test_openfoam_adapter.py` green
- [ ] `aero run naca0012 --executor local-ssh` returns Cd ≈ 0.0079 ± 25% in
      <10min on the configured LXC
- [ ] MLflow UI on `aero-mlflow` shows the run with the three tags (note: MLflow
      tracking server may not yet be wired in Stage 03 — if not, log to local
      `mlruns/` and add a TODO ADR pointing to Stage 04 to wire the remote server)
- [ ] `tests/stage_03/test_naca0012_smoke.py` passes (slow, marked appropriately)
- [ ] `vv-smoke` GitHub Action runs the smoke test on a self-hosted runner
      (operator may need to register one) — or marked skipped on hosted runners
      with a TODO ADR for Stage 13 to wire self-hosted runners properly
- [ ] ADR-003 committed with explicit out-of-scope list
- [ ] README quick-start updated
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.3`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The OpenFOAM version pin (operator may have institutional preference)
- The choice of NACA 0012 case parameters if you deviate from Re=6e6/Mach 0.15
- Adding any non-trivial package to base `aero` (vs `aero[openfoam]`)

## POST-STAGE HANDOFF

Required emphases:

- **Performance numbers**: SIF build time, single-run wall-clock, mesh cell count,
  iteration count to convergence.
- **Reproducibility check**: run the case twice, confirm Cd is bit-for-bit
  identical (or document why not).
- **Open items for Stage 04**: which provenance fields are missing
  (`dvc_input_hash`, `config_hash`) and where they slot in.
- **Open items for Stage 05**: the V&V tolerance band used here (±25%) is way too
  loose for thesis work — Stage 05 tightens this against TMR reference data.
- **Gotchas**: pyfoam API quirks, Ofpp edge cases, Apptainer + tmux interactions.
