"""The solver-agnostic adapter base — the `Solver` protocol and its shared types.

Stage 06 generalised the solver abstraction from its *second* concrete
implementation (SU2). Stage 07 promotes it once more, having added PyFR and
NekRS — GPU-resident, time-accurate, DOF-counting, periodic-domain-friendly
solvers — as the third and fourth data points (ADR-007). Three Stage-06
assumptions could not survive that promotion: `MeshHandle.n_cells` was renamed
to `n_elements` (with a sibling `n_dof` for FR/SEM); `SolveResult.cd`/`.cl`
became optional (Taylor-Green and periodic hill are not airfoils); and the
typed `history` is now a `ConvergenceHistory | TimeHistory` discriminated union
covering both steady-state and time-accurate solves (CONSTITUTION Invariant 7
— TYPED-SOLVE-HISTORY). `build_apptainer_exec` gained `gpu=True` (for `--nv`)
and `mpi_n=N` (for `mpirun -n N`) so GPU+MPI launch is uniform across PyFR,
NekRS and the JAX-Fluids stage that follows.

`OpenFOAMSolver`, `SU2Solver`, `PyFRSolver` and `NekRSSolver` all subclass the
`Solver` ABC and all satisfy the `SolverProtocol` structural contract the V&V
harness types against. The shape is now the *intersection* of all four
adapters — but the door is left open: `mesh()` and `run()` stay abstract
because their post-command verification still differs enough to make
hoisting only the command-string into a template method near-pointless.

This module is PLATFORM-NOT-HUB clean: it imports only stdlib, numpy, pydantic,
loguru and `aero.orchestration._base`. No solver library, no `xarray`.
"""

from __future__ import annotations

import abc
import shlex
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import numpy as np
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.orchestration._base import Executor

# --- platform paths -----------------------------------------------------------
# The aero NFS dataset is mounted at different points on the CLI host and inside
# the aero LXC; a case written on one side is read on the other.
DEFAULT_HOST_NFS_ROOT = Path("/mnt/aero-nfs")
DEFAULT_REMOTE_NFS_ROOT = Path("/mnt/aero")
RUNS_SUBDIR = "runs"
CASE_BIND_TARGET = "/case"  # where the case dir is bind-mounted inside a SIF

# Shared strict pydantic config — see .claude/rules/fail-loud-pydantic.md.
_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


# --- the apptainer-exec command builder ---------------------------------------
def build_apptainer_exec(
    *,
    sif_path: str,
    case_bind_source: str,
    command: str,
    case_bind_target: str = CASE_BIND_TARGET,
    writable_tmpfs: bool = False,
    env: Mapping[str, str] | None = None,
    gpu: bool = False,
    mpi_n: int | None = None,
) -> str:
    """Compose the `apptainer exec` command line that runs one solver command.

    The case directory is bind-mounted to `case_bind_target` inside the SIF;
    `command` runs there via a *login* shell (`bash -lc`) because solver images
    commonly activate their environment through `/etc/profile.d`. Pure and
    deterministic — this is the seam the adapter unit tests pin. Shared by
    every `Solver`: OpenFOAM (`blockMesh`/`simpleFoam`), SU2 (`SU2_CFD`), PyFR
    (`pyfr run -b cuda`) and NekRS (`nekrs --setup ... --backend CUDA`) each
    run exactly one bind-mounted, login-shell command in a signed SIF.

    `writable_tmpfs=True` adds `--writable-tmpfs` so the container gets a
    writable `/tmp` — OpenMPI's session-dir setup (SU2, NekRS) needs this,
    OpenFOAM doesn't. `env` is a mapping of environment-variable name → value
    prepended to the inner shell command so they affect that one solver
    invocation without touching apptainer's own env passthrough.

    `gpu=True` appends `--nv` so the container sees the host's NVIDIA driver
    (Stage-07 PyFR `-b cuda`, NekRS OCCA CUDA backend, the Stage-08 JAX-Fluids
    GPU path). `mpi_n=N` wraps `command` in `mpirun -n N <command>` for
    multi-rank GPU runs (NekRS multi-GPU, PyFR multi-rank). Defaults preserve
    the Stage-03/Stage-06 command-strings byte-for-byte: existing
    OpenFOAM/SU2 callers pass neither and get identical output.
    """
    if mpi_n is not None and mpi_n < 1:
        raise ValueError(f"mpi_n must be >= 1, got {mpi_n}")
    inner_cmd = f"mpirun -n {mpi_n} {command}" if mpi_n is not None else command
    env_prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in (env or {}).items())
    inner = f"cd {shlex.quote(case_bind_target)} && {env_prefix}{inner_cmd}"
    flags = ""
    if writable_tmpfs:
        flags += "--writable-tmpfs "
    if gpu:
        flags += "--nv "
    return (
        f"apptainer exec {flags}--bind "
        f"{shlex.quote(case_bind_source)}:{shlex.quote(case_bind_target)} "
        f"{shlex.quote(sif_path)} bash -lc {shlex.quote(inner)}"
    )


# --- structural contracts -----------------------------------------------------
@runtime_checkable
class SpecLike(Protocol):
    """The minimal contract every solver case spec satisfies: a name.

    `name` is the only spec attribute cross-solver code reads (it forms the
    `run_id`). Each adapter keeps its own precise, strict-typed spec model
    (`CaseSpec`, `SU2CaseSpec`, ...); `SpecLike` is the honest minimum `_base`
    may rely on.
    """

    name: str


# --- shared lifecycle handle models -------------------------------------------
class CaseDir(BaseModel):
    """A prepared solver case directory on the shared NFS dataset.

    The same bytes are visible at `host_path` (where the aero process wrote
    them) and at `remote_path` (where the SIF reads them inside the LXC).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
        arbitrary_types_allowed=True,  # `spec` is validated structurally (SpecLike)
    )

    run_id: str = Field(..., min_length=1, description="Unique run identifier.")
    spec: SpecLike = Field(..., description="The spec this case was built from.")
    host_path: Path = Field(..., description="Case path as seen by the aero process.")
    remote_path: Path = Field(..., description="Case path as seen inside the LXC/SIF.")


class MeshHandle(BaseModel):
    """Outcome of a solver's `mesh` step.

    `n_elements` is the count of solver-native primitives — FV cells for
    OpenFOAM/SU2, spectral / FR elements for NekRS/PyFR (Stage-07 rename of
    the Stage-06 `n_cells`; the cleaner name lets the same field carry every
    solver's element count uniformly). `n_dof` is the distinct degrees of
    freedom — for FR/SEM solvers this equals `n_elements * (p+1)**d` (with `p`
    the polynomial order and `d` the spatial dimension); for FV solvers it is
    left `None` to encode "same as the element count".
    """

    model_config = _STRICT

    case_dir: CaseDir = Field(..., description="The meshed case.")
    ok: bool = Field(..., description="True iff meshing succeeded.")
    n_elements: int | None = Field(
        default=None, description="Solver-native element count, if reported."
    )
    n_dof: int | None = Field(
        default=None, description="Distinct DOF count (FR/SEM); None for FV solvers."
    )


class ResultHandle(BaseModel):
    """Outcome of a solver's `run` step — the raw, not-yet-parsed solve."""

    model_config = _STRICT

    case_dir: CaseDir = Field(..., description="The solved case.")
    returncode: int = Field(..., description="Solver exit code; 0 is success.")
    output_host_path: Path = Field(
        ...,
        description="Directory holding the solve's machine-readable output, host-side.",
    )
    solver_log: str = Field(default="", description="Captured solver stdout.")


# --- solver-neutral result types ----------------------------------------------
class ConvergenceHistory(BaseModel):
    """Steady-state branch of the typed solve-history discriminated union.

    A monitored-residual trace — one residual per solver iteration. `iteration`
    and `residual` are paired and equal-length; `iteration` ascends. The
    `kind="convergence"` discriminator lets `SolveResult.history` carry either
    this or a `TimeHistory` while keeping the V&V harness's parsing typed
    (CONSTITUTION Invariant 7 — TYPED-SOLVE-HISTORY).
    """

    model_config = _STRICT

    kind: Literal["convergence"] = Field(
        default="convergence", description="Discriminator for the SolveResult.history union."
    )
    iteration: tuple[int, ...] = Field(..., description="Solver iteration index, ascending.")
    residual: tuple[float, ...] = Field(
        ..., description="Monitored residual, paired with `iteration`."
    )

    @model_validator(mode="after")
    def _paired(self) -> ConvergenceHistory:
        if len(self.iteration) != len(self.residual):
            raise ValueError(
                "iteration and residual differ in length: "
                f"{len(self.iteration)} vs {len(self.residual)}"
            )
        if not self.iteration:
            raise ValueError("a ConvergenceHistory needs at least one sample")
        return self


class TimeHistory(BaseModel):
    """Time-accurate branch of the typed solve-history discriminated union.

    A monitor trace from a time-accurate solve — one sample per output time.
    `monitor_name` names what `monitor` is (e.g. `'dissipation_rate'` for
    Taylor-Green vortex, `'separation_length'` for periodic hill). `t` is
    measured in the solver's native time unit (convective time units for PyFR
    Taylor-Green, dimensionless time for NekRS). The `kind="time"`
    discriminator lets the V&V harness dispatch typed against either history
    branch (Invariant 7).
    """

    model_config = _STRICT

    kind: Literal["time"] = Field(
        default="time", description="Discriminator for the SolveResult.history union."
    )
    t: tuple[float, ...] = Field(..., description="Output times, ascending.")
    monitor: tuple[float, ...] = Field(..., description="Monitor value, paired with `t`.")
    monitor_name: str = Field(
        ..., min_length=1, description="What `monitor` is (e.g. 'dissipation_rate')."
    )

    @model_validator(mode="after")
    def _paired(self) -> TimeHistory:
        if len(self.t) != len(self.monitor):
            raise ValueError(
                f"t and monitor differ in length: {len(self.t)} vs {len(self.monitor)}"
            )
        if not self.t:
            raise ValueError("a TimeHistory needs at least one sample")
        return self


class SolveResult(BaseModel):
    """The typed, solver-neutral result of a completed CFD solve.

    Every `Solver.load()` returns this — never a solver-native container
    (`xarray.Dataset`, a raw dict, a CSV path) — so the V&V harness, the
    cross-solver comparison and the Stage-12 UQ layer all read one shape
    (CONSTITUTION Invariant 7 — TYPED-SOLVE-HISTORY).

    Stage-07 promoted `cd`/`cl` to `Optional`: Taylor-Green and periodic hill
    are not airfoils, so requiring those force coefficients would force fake
    values into scale-resolving cases. Cases that need them (every airfoil
    V&V case) `assert result.cd is not None` at the top of their `evaluate()`.
    `scalars` carries case-specific scalar outputs (Taylor-Green peak
    dissipation rate, periodic-hill re-attachment length, ...) without
    needing one boolean-flagged field per case.
    """

    model_config = _STRICT

    run_id: str = Field(..., min_length=1, description="The run this result came from.")
    case_name: str = Field(..., min_length=1, description="The case that was solved.")
    cd: float | None = Field(
        default=None, description="Converged drag coefficient, if the case defines one."
    )
    cl: float | None = Field(
        default=None, description="Converged lift coefficient, if the case defines one."
    )
    cd_pressure: float | None = Field(
        default=None,
        description="Pressure (form) drag-coefficient component, if the solve emits a "
        "force decomposition. cd_pressure + cd_viscous reconstructs cd.",
    )
    cd_viscous: float | None = Field(
        default=None,
        description="Viscous (skin-friction) drag-coefficient component, if the solve "
        "emits a force decomposition. cd_pressure + cd_viscous reconstructs cd.",
    )
    iterations_to_convergence: int = Field(..., gt=0, description="Iterations the solve ran.")
    final_residual: float = Field(
        ...,
        description=(
            "Last monitored residual (equals `history.residual[-1]` for a steady "
            "convergence; the final monitor value for a time-accurate run)."
        ),
    )
    history: ConvergenceHistory | TimeHistory = Field(
        ..., discriminator="kind", description="The typed solve-history trace."
    )
    scalars: dict[str, float] = Field(
        default_factory=dict,
        description="Case-specific scalar outputs (e.g. peak dissipation, separation length).",
    )
    source: str = Field(..., min_length=1, description="The file `load()` parsed.")


class WallDistribution(BaseModel):
    """Cf and Cp sampled along a wall patch, ordered by streamwise coordinate.

    A `Solver.wall_distribution()` return value — solver-neutral so the V&V
    cases compare surface distributions without naming a concrete adapter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    patch: str = Field(..., min_length=1, description="The sampled wall patch.")
    x: list[float] = Field(..., description="Streamwise coordinate, ascending.")
    cp: list[float] = Field(..., description="Pressure coefficient, paired with `x`.")
    cf: list[float] = Field(..., description="Skin-friction coefficient, paired with `x`.")

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """`(x, cp, cf)` as numpy arrays."""
        return np.asarray(self.x), np.asarray(self.cp), np.asarray(self.cf)


# --- the Solver base ----------------------------------------------------------
class Solver(abc.ABC):
    """Template-method base for a CFD solver adapter.

    Owns the shared lifecycle machinery (run-id/path computation, the `prepare`
    skeleton); declares the solver-specific seams (`_write_case`, `mesh`, `run`,
    `load`, `wall_distribution`) abstract. `OpenFOAMSolver` and `SU2Solver`
    subclass it. The lifecycle is `prepare -> mesh -> run -> load`, with
    `wall_distribution` an extra reader for cases that compare surface
    distributions.

    `mesh` and `run` are abstract rather than template methods on purpose: even
    with four concrete solvers (OpenFOAM, SU2, PyFR, NekRS) their post-command
    verification differs enough — polyMesh existence vs. SU2 `NELEM` parse vs.
    PyFR `pyfr import` + `pyfr partition` vs. NekRS `.re2` header parse — that
    hoisting only the command-string construction would leave a near-empty
    base method. See ADR-006 §6 and ADR-007 for the resolution at the
    third/fourth data point.
    """

    def __init__(
        self,
        *,
        sif_path: str,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
    ) -> None:
        self.sif_path = sif_path
        self.host_nfs_root = Path(host_nfs_root)
        self.remote_nfs_root = Path(remote_nfs_root)

    # --- shared concrete lifecycle ---
    def _new_run_paths(self, case: SpecLike) -> tuple[str, Path, Path]:
        """`(run_id, host_path, remote_path)` for a fresh run of `case`."""
        run_id = f"{case.name}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
        return (
            run_id,
            self.host_nfs_root / RUNS_SUBDIR / run_id,
            self.remote_nfs_root / RUNS_SUBDIR / run_id,
        )

    def prepare(self, case: SpecLike) -> CaseDir:
        """Write the solver case onto the shared NFS dataset (template method).

        Computes the run id and host/remote paths, delegates the case-file
        writing to the adapter's `_write_case`, and returns the `CaseDir`.
        """
        run_id, host_path, remote_path = self._new_run_paths(case)
        logger.info("preparing case {} at {}", run_id, host_path)
        self._write_case(case, host_path)
        return CaseDir(run_id=run_id, spec=case, host_path=host_path, remote_path=remote_path)

    # --- solver-specific seams ---
    @abc.abstractmethod
    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        """Write the solver's input files (mesh, config) under `host_path`."""

    @abc.abstractmethod
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Generate or validate the mesh for `case_dir`."""

    @abc.abstractmethod
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run the solver on `case_dir` (long-running, via the executor)."""

    @abc.abstractmethod
    def load(self, result: ResultHandle) -> SolveResult:
        """Parse a finished solve into a typed, solver-neutral `SolveResult`."""

    @abc.abstractmethod
    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution:
        """Extract the Cf/Cp distribution along wall `patch` from a finished solve.

        `u_inf` is the reference speed for the Cp/Cf non-dimensionalisation (default
        1.0, the platform's dimensionless convention; a dimensional case passes its own).
        """


@runtime_checkable
class SolverProtocol(Protocol):
    """The structural contract a solver must satisfy to drive the V&V harness.

    `aero.vv` types against this Protocol, never against the `Solver` ABC or a
    concrete adapter — so the harness imports no solver library and a test
    double or a Stage-09 surrogate can satisfy it too. The `Solver` ABC
    structurally satisfies this Protocol.
    """

    def prepare(self, case: SpecLike) -> CaseDir: ...
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle: ...
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle: ...
    def load(self, result: ResultHandle) -> SolveResult: ...
    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution: ...
