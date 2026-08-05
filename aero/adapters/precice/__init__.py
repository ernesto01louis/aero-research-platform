"""preCICE partitioned fluid-structure coupling (Stage 19; ADR-016/035/036).

The platform's fifth *kind* of solver adapter: not a solver, but the orchestration,
provenance and verification surface around two solvers that are coupled at run time.
Everything here is stdlib + numpy + pydantic. ``pyprecice`` is imported lazily and only
by :mod:`aero.adapters.precice.solverdummy`, which runs inside the SIF — importing this
package with no extras installed must stay clean (Invariant 1, enforced by the
``import-platform-only`` CI job).

Module map:

* :mod:`.config` — typed reader/validator for ``precice-config.xml`` and the single
  permitted mutation (``<max-time>``)
* :mod:`.case` — the coupled-case spec and digest-verified materialization of the pinned
  upstream tutorial
* :mod:`.launcher` — concurrent participant launch under a supervisor that always records
  why the run stopped
* :mod:`.watchpoint` — preCICE watch-point output into :class:`aero.postprocess.Signal`
* :mod:`.logs` — coupling iteration logs and the fail-loud convergence gate
* :mod:`.solver` — :class:`PreciceCoupledSolver`, the ``Solver`` lifecycle implementation
* :mod:`.solverdummy` — the two-participant infrastructure pre-flight
* :mod:`.template` — render an AUTHORED ``precice-config.xml`` from committed,
  digest-pinned bytes, and close the loop by re-reading it (Stage 20)
"""

from __future__ import annotations

from aero.adapters.precice.case import (
    CASE_ROOT_DIRNAME,
    AuthoredSource,
    CoupledCaseError,
    CoupledCaseSpec,
    DeclaredMutation,
    MaterializedTree,
    ParticipantSpec,
    TutorialPin,
    TutorialSource,
    materialize_tutorial,
    select_fluid_mesh,
)
from aero.adapters.precice.config import (
    PreciceConfig,
    PreciceConfigError,
    PreciceConfigExpectation,
    assert_config,
    read_precice_config,
    rewrite_max_time,
)
from aero.adapters.precice.launcher import (
    CoupledLaunchError,
    CoupledLaunchPlan,
    CoupledRunResult,
    ParticipantOutcome,
    build_participant_command,
    launch_coupled,
    render_supervisor_script,
)
from aero.adapters.precice.logs import (
    CouplingConvergenceError,
    CouplingIterationReport,
    assert_coupling_converged,
    read_iterations_log,
)
from aero.adapters.precice.solver import (
    DEFAULT_PRECICE_SIF_PATH,
    PreciceCoupledSolver,
    PreciceSolverError,
)
from aero.adapters.precice.template import (
    HG2007_TEMPLATE,
    RENDERER_VERSION,
    PreciceConfigValues,
    hg2007_expectation,
    read_template,
    render_precice_config,
    template_sha256,
    write_precice_config,
)
from aero.adapters.precice.watchpoint import (
    WatchpointError,
    WatchpointTrace,
    read_watchpoint,
)

#: The pyprecice pin, in one place. `aero[precice]`, the SIF's install and ADR-035 all
#: state this version, and `tests/unit/test_precice_pin_sync.py` asserts they agree —
#: an ABI mismatch between the bindings and the preCICE library inside the SIF is a
#: silent-wrong-answer class of bug, not a loud one.
PINNED_PYPRECICE_VERSION = "3.4.0"

#: The preCICE C++ library the SIF installs (Ubuntu 24.04 "noble" package).
PINNED_PRECICE_VERSION = "3.4.1"

#: The OpenFOAM-preCICE adapter commit, taken from upstream's own attested
#: `tools/tests/reference_versions.yaml` at the pinned tutorials commit.
PINNED_OPENFOAM_ADAPTER_COMMIT = "2c3062ce941915616ac763371805c57e15e02466"

__all__ = [
    "CASE_ROOT_DIRNAME",
    "DEFAULT_PRECICE_SIF_PATH",
    "HG2007_TEMPLATE",
    "PINNED_OPENFOAM_ADAPTER_COMMIT",
    "PINNED_PRECICE_VERSION",
    "PINNED_PYPRECICE_VERSION",
    "RENDERER_VERSION",
    "AuthoredSource",
    "CoupledCaseError",
    "CoupledCaseSpec",
    "CoupledLaunchError",
    "CoupledLaunchPlan",
    "CoupledRunResult",
    "CouplingConvergenceError",
    "CouplingIterationReport",
    "DeclaredMutation",
    "MaterializedTree",
    "ParticipantOutcome",
    "ParticipantSpec",
    "PreciceConfig",
    "PreciceConfigError",
    "PreciceConfigExpectation",
    "PreciceConfigValues",
    "PreciceCoupledSolver",
    "PreciceSolverError",
    "TutorialPin",
    "TutorialSource",
    "WatchpointError",
    "WatchpointTrace",
    "assert_config",
    "assert_coupling_converged",
    "build_participant_command",
    "hg2007_expectation",
    "launch_coupled",
    "materialize_tutorial",
    "read_iterations_log",
    "read_precice_config",
    "read_template",
    "read_watchpoint",
    "render_precice_config",
    "render_supervisor_script",
    "rewrite_max_time",
    "select_fluid_mesh",
    "template_sha256",
    "write_precice_config",
]
