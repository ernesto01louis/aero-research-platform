"""The solver-agnostic adapter base — the `Solver` protocol and its shared types.

Stage 06 generalises the solver abstraction from its *second* concrete
implementation (SU2), per ADR-003/ADR-006: a single-solver interface is only a
restatement of that solver. `OpenFOAMSolver` and `SU2Solver` both subclass the
`Solver` ABC (a template-method lifecycle owning the shared concrete code) and
both satisfy the `SolverProtocol` structural contract the V&V harness types
against.

The shape here is the *intersection* of OpenFOAM-ESI and SU2 only — PyFR/NekRS/
JAX-Fluids (Stages 07-08) are deliberately not anticipated; the seams they will
break are flagged in the Stage-06 handoff.

This module is PLATFORM-NOT-HUB clean: it imports only stdlib, numpy, pydantic,
loguru and `aero.orchestration._base`. No solver library, no `xarray`.
"""

from __future__ import annotations

import abc
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

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
) -> str:
    """Compose the `apptainer exec` command line that runs one solver command.

    The case directory is bind-mounted to `case_bind_target` inside the SIF;
    `command` runs there via a *login* shell (`bash -lc`) because solver images
    commonly activate their environment through `/etc/profile.d`. Pure and
    deterministic — this is the seam the adapter unit tests pin. Shared by every
    `Solver`: OpenFOAM (`blockMesh`/`simpleFoam`) and SU2 (`SU2_CFD`) each run
    exactly one bind-mounted, login-shell command in a signed SIF.
    """
    inner = f"cd {shlex.quote(case_bind_target)} && {command}"
    return (
        f"apptainer exec --bind "
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
    """Outcome of a solver's `mesh` step."""

    model_config = _STRICT

    case_dir: CaseDir = Field(..., description="The meshed case.")
    ok: bool = Field(..., description="True iff meshing succeeded.")
    n_cells: int | None = Field(default=None, description="Cell count, if reported.")


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
    """A solve's monitored-residual trace — one residual per solver iteration.

    The typed convergence history every adapter's `load()` must produce
    (CONSTITUTION Invariant 7). `iteration` and `residual` are paired and
    equal-length; `iteration` ascends.
    """

    model_config = _STRICT

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


class SolveResult(BaseModel):
    """The typed, solver-neutral result of a converged CFD solve.

    Every `Solver.load()` returns this — never a solver-native container
    (`xarray.Dataset`, a raw dict, a CSV path) — so the V&V harness, the
    cross-solver comparison and the Stage-12 UQ layer all read one shape
    (CONSTITUTION Invariant 7).
    """

    model_config = _STRICT

    run_id: str = Field(..., min_length=1, description="The run this result came from.")
    case_name: str = Field(..., min_length=1, description="The case that was solved.")
    cd: float = Field(..., description="Converged drag coefficient.")
    cl: float = Field(..., description="Converged lift coefficient.")
    iterations_to_convergence: int = Field(..., gt=0, description="Iterations the solve ran.")
    final_residual: float = Field(
        ..., description="Last monitored residual (equals `history.residual[-1]`)."
    )
    history: ConvergenceHistory = Field(..., description="The monitored-residual trace.")
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

    `mesh` and `run` are abstract rather than template methods on purpose: with
    only two solvers their post-command verification differs enough that
    hoisting only the command-string construction would leave a near-empty base
    method. Revisit at the third solver (PyFR, Stage 07). See ADR-006.
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
    def wall_distribution(self, result: ResultHandle, *, patch: str) -> WallDistribution:
        """Extract the Cf/Cp distribution along wall `patch` from a finished solve."""


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
    def wall_distribution(self, result: ResultHandle, *, patch: str) -> WallDistribution: ...
