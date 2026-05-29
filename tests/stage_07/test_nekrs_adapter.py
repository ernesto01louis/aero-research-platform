"""Unit tests for the NekRS adapter — Stage 07.

Like the PyFR tests, these cover only the host-side surface area; the
cluster-bound `nekrs` exercise lives in `tests/vv/test_taylor_green_nekrs.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters._base import SolverProtocol
from aero.adapters._meshing.nekmesh_wrapper import write_taylor_green_box
from aero.adapters.nekrs import NekRSSolver, NekRSTaylorGreenSpec
from aero.adapters.nekrs.case_writer import (
    write_taylor_green_par,
    write_taylor_green_udf,
)

pytestmark = pytest.mark.stage_07


def test_nekrs_solver_satisfies_solver_protocol() -> None:
    solver = NekRSSolver(sif_path="/dev/null")
    assert isinstance(solver, SolverProtocol)


def test_nekrs_taylor_green_spec_defaults() -> None:
    spec = NekRSTaylorGreenSpec(name="tg")
    assert spec.reynolds == 1600.0
    assert spec.n_elements_per_dir == 8
    assert spec.polynomial_order == 7
    assert spec.backend == "CUDA"


def test_nekrs_spec_rejects_unknown_backend() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NekRSTaylorGreenSpec(name="tg", backend="OPENCL")  # type: ignore[arg-type]


def test_taylor_green_box_writer_emits_periodic_codes(tmp_path: Path) -> None:
    """The `.box` file declares uniform N^3 spacing + all-periodic BCs."""
    box = tmp_path / "taylorGreen.box"
    n_hex = write_taylor_green_box(box, case_name="taylorGreen", n_elements_per_dir=4)
    assert n_hex == 4**3
    text = box.read_text(encoding="utf-8")
    # Negative N triple = uniform spacing in (x, y, z)
    assert "-4 -4 -4" in text
    # All six boundary codes set to P (periodic)
    assert "P  ,P  ,P  ,P  ,P  ,P" in text


def test_taylor_green_box_writer_rejects_degenerate_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="n_elements_per_dir must be >= 2"):
        write_taylor_green_box(tmp_path / "x.box", case_name="x", n_elements_per_dir=1)


def test_taylor_green_par_writer_includes_periodic_bcs(tmp_path: Path) -> None:
    spec = NekRSTaylorGreenSpec(name="tg", n_elements_per_dir=4, polynomial_order=5)
    out = tmp_path / "tg.par"
    write_taylor_green_par(out, spec)
    par = out.read_text(encoding="utf-8")
    assert "polynomialOrder = 5" in par
    assert "boundaryTypeMap = periodic, periodic, periodic, periodic, periodic, periodic" in par


def test_taylor_green_udf_writer_emits_brachet_ic_and_monitor(tmp_path: Path) -> None:
    spec = NekRSTaylorGreenSpec(name="tg")
    out = tmp_path / "tg.udf"
    write_taylor_green_udf(out, spec)
    udf = out.read_text(encoding="utf-8")
    # The Brachet analytic IC and the rank-0 KE printer
    assert "sin(x[i]) * cos(y[i]) * cos(z[i])" in udf
    assert "gradKE: t=%.6e tstep=%d ke=%.10e" in udf


def test_nekrs_solver_write_case_creates_all_three_files(tmp_path: Path) -> None:
    solver = NekRSSolver(sif_path="/dev/null", host_nfs_root=tmp_path)
    spec = NekRSTaylorGreenSpec(name="tg-tw")
    case_dir = solver.prepare(spec)
    # case_name defaults to "taylorGreen"
    for ext in ("box", "par", "udf"):
        assert (case_dir.host_path / f"taylorGreen.{ext}").is_file()


def test_nekrs_solver_rejects_wrong_spec(tmp_path: Path) -> None:
    solver = NekRSSolver(sif_path="/dev/null", host_nfs_root=tmp_path)

    class _Foreign:
        name = "x"

    with pytest.raises(TypeError, match="cannot handle spec"):
        solver._write_case(_Foreign(), tmp_path)


def test_nekrs_wall_distribution_raises_for_periodic_case(tmp_path: Path) -> None:
    from aero.adapters._base import CaseDir, ResultHandle

    solver = NekRSSolver(sif_path="/dev/null", host_nfs_root=tmp_path)
    case_dir = CaseDir(
        run_id="t",
        spec=NekRSTaylorGreenSpec(name="tg"),
        host_path=tmp_path,
        remote_path=Path("/mnt/aero/test"),
    )
    result = ResultHandle(case_dir=case_dir, returncode=0, output_host_path=tmp_path)
    with pytest.raises(NotImplementedError, match="periodic"):
        solver.wall_distribution(result, patch="wall")
