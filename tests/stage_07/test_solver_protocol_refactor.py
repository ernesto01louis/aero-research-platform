"""Stage-07 protocol-refactor invariants.

Locks in the additive Stage-07 promotions to `aero.adapters._base`:
  * `MeshHandle.n_elements` + `MeshHandle.n_dof` (renamed from `n_cells`);
  * `TimeHistory` joins `ConvergenceHistory` in the typed solve-history
    discriminated union — `SolveResult.history` accepts either;
  * `SolveResult.cd` / `.cl` are `float | None`;
  * `SolveResult.scalars: dict[str, float]` for case-specific outputs;
  * `build_apptainer_exec(gpu=True)` appends `--nv`;
  * `build_apptainer_exec(mpi_n=N)` wraps the inner command in `mpirun -n N`.

These guard against accidental Stage-08+ regressions of the
TYPED-SOLVE-HISTORY invariant (CONSTITUTION Invariant 7, amended).
"""

from __future__ import annotations

import pytest
from aero.adapters._base import (
    ConvergenceHistory,
    MeshHandle,
    SolveResult,
    TimeHistory,
    build_apptainer_exec,
)

pytestmark = pytest.mark.stage_07


# --- MeshHandle ---------------------------------------------------------------
def test_mesh_handle_n_elements_and_n_dof_are_independent() -> None:
    """FV: only n_elements; FR/SEM: both. Both default to None."""
    from aero.adapters._base import CaseDir

    case_dir = _fake_case_dir()
    h_fv = MeshHandle(case_dir=case_dir, ok=True, n_elements=4242)
    assert h_fv.n_elements == 4242
    assert h_fv.n_dof is None

    h_fr = MeshHandle(case_dir=case_dir, ok=True, n_elements=512, n_dof=512 * 4**3)
    assert h_fr.n_elements == 512
    assert h_fr.n_dof == 512 * 64
    _ = CaseDir  # silence linter; imported via helper


def test_mesh_handle_rejects_legacy_n_cells_keyword() -> None:
    """The Stage-06 `n_cells=` constructor keyword is gone; extra='forbid' fires."""
    case_dir = _fake_case_dir()
    with pytest.raises(Exception, match="n_cells"):
        MeshHandle(case_dir=case_dir, ok=True, n_cells=42)  # type: ignore[call-arg]


# --- TimeHistory --------------------------------------------------------------
def test_time_history_pairs_t_and_monitor() -> None:
    th = TimeHistory(t=(0.0, 0.1, 0.2), monitor=(1.0, 0.9, 0.8), monitor_name="dissipation")
    assert th.kind == "time"
    assert len(th.t) == len(th.monitor)
    assert th.monitor_name == "dissipation"


def test_time_history_rejects_mismatched_lengths() -> None:
    with pytest.raises(Exception, match="differ in length"):
        TimeHistory(t=(0.0, 0.1, 0.2), monitor=(1.0,), monitor_name="x")


def test_time_history_rejects_empty() -> None:
    with pytest.raises(Exception, match="at least one sample"):
        TimeHistory(t=(), monitor=(), monitor_name="x")


# --- SolveResult discriminated union -----------------------------------------
def test_solve_result_accepts_convergence_history() -> None:
    history = ConvergenceHistory(iteration=(1, 2, 3), residual=(1e-2, 1e-4, 1e-6))
    sr = SolveResult(
        run_id="t",
        case_name="naca0012",
        cd=0.0083,
        cl=0.0,
        iterations_to_convergence=3,
        final_residual=1e-6,
        history=history,
        source="postProcessing/forceCoeffs",
    )
    assert sr.history.kind == "convergence"
    assert sr.scalars == {}
    assert sr.cd == 0.0083


def test_solve_result_accepts_time_history() -> None:
    history = TimeHistory(t=(0.0, 0.1, 0.2), monitor=(1e-3, 2e-3, 3e-3), monitor_name="diss")
    sr = SolveResult(
        run_id="t",
        case_name="taylor_green_p3_32",
        iterations_to_convergence=3,
        final_residual=3e-3,
        history=history,
        scalars={"peak_dissipation": 3e-3},
        source="out/integrate.csv",
    )
    assert sr.history.kind == "time"
    assert sr.cd is None
    assert sr.cl is None
    assert sr.scalars["peak_dissipation"] == pytest.approx(3e-3)


def test_solve_result_discriminator_round_trips() -> None:
    """JSON round-trip preserves the discriminated-union branch."""
    history = TimeHistory(t=(0.0, 1.0), monitor=(0.5, 0.4), monitor_name="diss")
    sr = SolveResult(
        run_id="rt",
        case_name="tg",
        iterations_to_convergence=2,
        final_residual=0.4,
        history=history,
        source="x.csv",
    )
    raw = sr.model_dump_json()
    sr2 = SolveResult.model_validate_json(raw)
    assert sr2.history.kind == "time"
    assert isinstance(sr2.history, TimeHistory)
    assert sr2.history.monitor_name == "diss"


# --- build_apptainer_exec extensions ------------------------------------------
def test_build_apptainer_exec_gpu_appends_nv() -> None:
    cmd = build_apptainer_exec(
        sif_path="/x.sif",
        case_bind_source="/case",
        command="pyfr run -b cuda solver.ini mesh.pyfrm",
        gpu=True,
    )
    assert " --nv " in cmd
    assert "pyfr run -b cuda" in cmd


def test_build_apptainer_exec_mpi_n_wraps_in_mpirun() -> None:
    cmd = build_apptainer_exec(
        sif_path="/x.sif",
        case_bind_source="/case",
        command="nekrs --setup tg --backend CUDA",
        mpi_n=4,
    )
    assert "mpirun -n 4 nekrs --setup tg --backend CUDA" in cmd


def test_build_apptainer_exec_mpi_n_rejects_zero() -> None:
    with pytest.raises(ValueError, match="mpi_n must be >= 1"):
        build_apptainer_exec(sif_path="/x.sif", case_bind_source="/c", command="x", mpi_n=0)


def test_build_apptainer_exec_defaults_byte_compatible_with_stage06() -> None:
    """OpenFOAM/SU2 call sites — no gpu, no mpi_n — produce the Stage-06 form."""
    cmd = build_apptainer_exec(sif_path="/x.sif", case_bind_source="/case", command="blockMesh")
    # No --nv, no mpirun, no --writable-tmpfs
    assert "--nv" not in cmd
    assert "mpirun" not in cmd
    assert "--writable-tmpfs" not in cmd


# --- helpers ------------------------------------------------------------------
def _fake_case_dir() -> object:
    """Build a minimal CaseDir for MeshHandle's required `case_dir` field."""
    from pathlib import Path

    from aero.adapters._base import CaseDir

    class _MinSpec:
        name = "t"

    return CaseDir(
        run_id="t",
        spec=_MinSpec(),
        host_path=Path("/tmp/aero-test"),
        remote_path=Path("/mnt/aero/test"),
    )
