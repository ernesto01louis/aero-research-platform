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

This module is PLATFORM-NOT-HUB clean: it imports only stdlib, numpy, pydantic and
`aero.orchestration._base`. No solver library, no `xarray`. loguru is imported lazily at
its one call site (Stage 21, ADR-049 H-12): `aero.vv` imports this module, so a
module-level import put loguru on the import path of `aero.vv.reportable` and of the
result-crate reader, which must load with only stdlib + numpy + pydantic.
"""

from __future__ import annotations

import abc
import secrets
import shlex
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from aero.orchestration._base import Executor
from aero.provenance.four_fold import (
    SIF_VERIFIED_AT_LAUNCH_V1,
    ProvenanceError,
    ProvenanceTupleV2,
)

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


# --- the launch guard (ADR-053) ------------------------------------------------
#: The exit status of a refused launch, and the two lines the guard writes to stderr.
SIF_REFUSED_EXIT = 86
SIF_REFUSED_MARK = "AERO-SIF-REFUSED"
SIF_VERIFIED_MARK = "AERO-SIF-VERIFIED"


class SifPin(BaseModel):
    """The SIF one command launches, and the digest the run's tuple names for it (ADR-053).

    Only `CaseDir.pin` builds one, from the run's `ProvenanceTupleV2`, so the digest a command is
    checked against is the digest the run records, never one re-derived from the path.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True, validate_default=True
    )

    path: str = Field(..., min_length=1, description="The SIF path apptainer is given.")
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$", description="The digest it must hash to.")

    @model_validator(mode="after")
    def _one_line(self) -> SifPin:
        if "\n" in self.path or "\r" in self.path:
            raise ValueError(f"a SIF path may not contain a line break: {self.path!r}")
        return self


def sif_guard(pin: SifPin) -> str:
    """The shell prefix that hashes the SIF on the solve host before apptainer opens it.

    A mismatch, or a missing file, writes `AERO-SIF-REFUSED` and exits 86 before apptainer
    starts; a match writes `AERO-SIF-VERIFIED` and runs the command. HEX and PATH are `printf`
    arguments, never part of a format string, and the prefix never contains the literal
    `apptainer exec ` (ADR-053).
    """
    path = shlex.quote(pin.path)
    return (
        f"{{ printf '%s  %s\\n' {pin.sha256} {path} | sha256sum --check --status - "
        f"|| {{ printf '{SIF_REFUSED_MARK} expected=%s path=%s\\n' {pin.sha256} {path} >&2; "
        f"exit {SIF_REFUSED_EXIT}; }}; }} "
        f"&& printf '{SIF_VERIFIED_MARK} sha256=%s path=%s\\n' {pin.sha256} {path} >&2 && "
    )


def raise_if_container_refused(result: Any) -> None:
    """Turn a refused launch into `ProvenanceError` — never a solver failure (ADR-053).

    Call it on every `ExecResult` of a guarded command before reading its return code: the
    refusal line is in `stderr` for a synchronous launch and in `stdout` for a detached one
    (run_long.sh merges the streams). A `ResultHandle` is scanned through its `solver_log`, so
    the V&V runner can check what any `SolverLike` returns.
    """
    text = "\n".join(
        str(getattr(result, attr, "") or "") for attr in ("stderr", "stdout", "solver_log")
    )
    refused = [line.strip() for line in text.splitlines() if SIF_REFUSED_MARK in line]
    if refused:
        raise ProvenanceError(
            f"the SIF did not hash to the digest this run records, so the launch was refused "
            f"before apptainer started (ADR-053): {refused[0]}"
        )


def assert_launches_guarded(case_dir: CaseDir, provenance: ProvenanceTupleV2) -> None:
    """Refuse to record a tuple the case's launches did not run under (ADR-053).

    The tuple logged must be the one the case was prepared with, since every launch was pinned
    from it; and a `sif-sha256-verified-at-launch/v1` record needs at least one guarded launch,
    or it would claim a check that never ran.
    """
    if case_dir.provenance != provenance:
        raise ProvenanceError(
            f"{case_dir.run_id}: the tuple being recorded is not the one the case was prepared "
            "with, so its launches were pinned from a different record (ADR-053)"
        )
    scheme = provenance.schemes.container_sif_sha256
    if scheme == SIF_VERIFIED_AT_LAUNCH_V1 and case_dir.guarded_launches == 0:
        raise ProvenanceError(
            f"{case_dir.run_id}: no launch of this run went through the SIF guard, so it "
            f"cannot be recorded under {scheme} (ADR-053)"
        )


# --- the apptainer-exec command builder ---------------------------------------
def build_apptainer_exec(
    *,
    expected: SifPin,
    case_bind_source: str,
    command: str,
    case_bind_target: str = CASE_BIND_TARGET,
    writable_tmpfs: bool = False,
    env: Mapping[str, str] | None = None,
    gpu: bool = False,
    mpi_n: int | None = None,
    no_home: bool = False,
) -> str:
    """Compose the guarded `apptainer exec` command line that runs one solver command.

    Since Stage 23 (ADR-053) the SIF is given as a `SifPin`: the command is the launch guard
    (`sif_guard`) followed by `apptainer exec … <pin.path> …`, so the file that is hashed and the
    file that is executed are the same bytes by construction.

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
    multi-rank GPU runs (NekRS multi-GPU, PyFR multi-rank).

    `no_home=True` puts `--no-home` first among the flags, exactly where the preCICE
    callers used to splice it in with `str.replace("apptainer exec ", …, 1)` (Stage 23
    made it structural, so no prefix can ever move the splice point).
    """
    if mpi_n is not None and mpi_n < 1:
        raise ValueError(f"mpi_n must be >= 1, got {mpi_n}")
    inner_cmd = f"mpirun -n {mpi_n} {command}" if mpi_n is not None else command
    env_prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in (env or {}).items())
    inner = f"cd {shlex.quote(case_bind_target)} && {env_prefix}{inner_cmd}"
    flags = "--no-home " if no_home else ""
    if writable_tmpfs:
        flags += "--writable-tmpfs "
    if gpu:
        flags += "--nv "
    return (
        f"{sif_guard(expected)}apptainer exec {flags}--bind "
        f"{shlex.quote(case_bind_source)}:{shlex.quote(case_bind_target)} "
        f"{shlex.quote(expected.path)} bash -lc {shlex.quote(inner)}"
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
    provenance: ProvenanceTupleV2 = Field(
        ...,
        description=(
            "The run's tuple, bound to the case (ADR-052 D1, ADR-053): every launch pins its SIF "
            "from it, and every declared-input read checks its declaration."
        ),
    )
    _guarded_launches: int = PrivateAttr(default=0)

    def pin(self, sif_path: str) -> SifPin:
        """The pin for one launch of `sif_path`; refused unless this run's tuple names the SIF.

        The digest comes from the tuple — the container of record, or a roster member — never
        from the path, so a solver configured with a different SIF than the run records (for
        example `aero run --solver su2` with the OpenFOAM SIF configured) is refused before any
        command is built.
        """
        name = Path(sif_path).name
        prov = self.provenance
        if prov.containers:
            digest = {ref.name: ref.sha256 for ref in prov.containers}.get(name)
        else:
            digest = prov.container_sif_sha256 if name == prov.container_sif_name else None
        if digest is None:
            named = [r.name for r in prov.containers] or [prov.container_sif_name]
            raise ProvenanceError(
                f"{name!r} is not a container this run's provenance names ({', '.join(named)}); "
                "refusing to launch a SIF the record would not describe (ADR-053)"
            )
        self._guarded_launches += 1
        return SifPin(path=sif_path, sha256=digest)

    @property
    def guarded_launches(self) -> int:
        """How many launch commands this case has pinned (the runner refuses a v1 record at 0)."""
        return self._guarded_launches


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
    failure: str = Field(
        default="",
        description=(
            "Why meshing failed, built by `aero.orchestration.describe_failure` at the point "
            "the executor result is known: the mesh command actually run, the exit code, stderr, "
            "and whether the host was reachable at all. Stage 20 — callers used to synthesise "
            "'blockMesh failed' from `ok=False` alone, which named the wrong component for every "
            "failure that was not blockMesh's."
        ),
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
        """`(run_id, host_path, remote_path)` for a fresh run of `case`, never an existing one.

        The run id names the case directory on the shared NFS dataset and the detached session.
        A timestamp alone collided (Stage 23): `vv-required` and `vv-smoke` started the same case
        in the same second, so both wrote and meshed one directory and the second submit was
        refused as a duplicate session. A random suffix makes ids unique, and a directory that
        already exists is refused, never reused.
        """
        run_id = f"{case.name}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        host_path = self.host_nfs_root / RUNS_SUBDIR / run_id
        if host_path.exists():
            raise FileExistsError(
                f"{host_path}: a run directory already exists; refusing to reuse it"
            )
        return run_id, host_path, self.remote_nfs_root / RUNS_SUBDIR / run_id

    def prepare(self, case: SpecLike, *, provenance: ProvenanceTupleV2) -> CaseDir:
        """Write the solver case onto the shared NFS dataset (template method).

        Computes the run id and host/remote paths, delegates the case-file
        writing to the adapter's `_write_case`, and returns the `CaseDir`, which
        carries the run's tuple: every launch pins its SIF from it (ADR-053).
        """
        if not isinstance(provenance, ProvenanceTupleV2):
            raise ProvenanceError(
                "prepare needs the run's ProvenanceTupleV2: launches are pinned from it (ADR-053)"
            )
        run_id, host_path, remote_path = self._new_run_paths(case)
        from loguru import logger  # lazy: keeps loguru off the core import path (H-12)

        logger.info("preparing case {} at {}", run_id, host_path)
        self._write_case(case, host_path)
        return CaseDir(
            run_id=run_id,
            spec=case,
            host_path=host_path,
            remote_path=remote_path,
            provenance=provenance,
        )

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

    def prepare(self, case: SpecLike, *, provenance: ProvenanceTupleV2) -> CaseDir: ...
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle: ...
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle: ...
    def load(self, result: ResultHandle) -> SolveResult: ...
    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution: ...
