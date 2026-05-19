"""Stage 06 — the generalised `Solver` protocol.

Pure, no cluster: asserts that both concrete adapters satisfy the structural
`SolverProtocol` the V&V harness types against, and that the `Solver` ABC
enforces its abstract seams. This is the structural check behind ADR-006.
"""

from __future__ import annotations

import abc

import pytest
from aero.adapters._base import (
    ConvergenceHistory,
    Solver,
    SolverProtocol,
)
from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.su2 import SU2Solver


@pytest.mark.stage_06
def test_openfoam_solver_satisfies_protocol() -> None:
    assert isinstance(OpenFOAMSolver(), SolverProtocol)


@pytest.mark.stage_06
def test_su2_solver_satisfies_protocol() -> None:
    assert isinstance(SU2Solver(), SolverProtocol)


@pytest.mark.stage_06
def test_both_adapters_subclass_the_solver_abc() -> None:
    assert issubclass(OpenFOAMSolver, Solver)
    assert issubclass(SU2Solver, Solver)


@pytest.mark.stage_06
def test_solver_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Solver(sif_path="/x.sif")  # type: ignore[abstract]


@pytest.mark.stage_06
def test_solver_abc_declares_the_five_seams() -> None:
    # The seams a third solver (PyFR, Stage 07) must implement.
    seams = {"_write_case", "mesh", "run", "load", "wall_distribution"}
    assert seams <= Solver.__abstractmethods__


@pytest.mark.stage_06
def test_partial_solver_stays_abstract() -> None:
    # A solver that implements only some seams must remain non-instantiable.
    class HalfSolver(Solver):
        def _write_case(self, case: object, host_path: object) -> None: ...

    assert isinstance(HalfSolver, abc.ABCMeta)
    with pytest.raises(TypeError):
        HalfSolver(sif_path="/x.sif")  # type: ignore[abstract]


@pytest.mark.stage_06
def test_convergence_history_must_be_paired_and_nonempty() -> None:
    ConvergenceHistory(iteration=(1, 2), residual=(1e-2, 1e-4))  # ok
    with pytest.raises(ValueError, match="differ in length"):
        ConvergenceHistory(iteration=(1, 2, 3), residual=(1e-2,))
    with pytest.raises(ValueError, match="at least one sample"):
        ConvergenceHistory(iteration=(), residual=())
